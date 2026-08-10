"""Offline-score raw and gate-separated A004 post-gate probe results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, median
from typing import Any

from Tools.core_freeze.e3_routing import a004_contract_adjudication as gate


CONFIG_PATH = Path(__file__).with_name("a004_postgate_probe_analysis_config_v1.json")


def validate_config(config: dict[str, Any]) -> None:
    if config["expected_result_count"] != 10:
        raise ValueError("analysis requires exactly ten terminal results")
    for field in ("tool_execution_allowed", "external_api_calls_allowed",
                  "confirmatory_inference_allowed", "causal_gate_benefit_claim_allowed",
                  "core_frozen"):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")


def analyze(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {name: gate.validate_binding(binding) for name, binding in config["bindings"].items()}
    docs = {name: gate.load_json(path) for name, path in paths.items()}
    raw_rows = docs["raw_results"]["results"]
    gate_rows = docs["gate_results"]["results"]
    gold_rows = docs["scoring_registry"]["tasks"]
    if not (len(raw_rows) == len(gate_rows) == len(gold_rows) == 10):
        raise ValueError("raw, gate and scoring dimensions differ")
    raw_by_id = {row["task_id"]: row for row in raw_rows}
    gate_by_id = {row["task_id"]: row for row in gate_rows}
    gold_by_id = {row["task_id"]: row for row in gold_rows}
    if len(raw_by_id) != 10 or set(raw_by_id) != set(gate_by_id) or set(raw_by_id) != set(gold_by_id):
        raise ValueError("task identifiers are incomplete or duplicated")
    scores = []
    for task_id in sorted(raw_by_id):
        raw = raw_by_id[task_id]
        gated = gate_by_id[task_id]["gate_decision"]
        gold = gold_by_id[task_id]
        calls = gate.parse_calls(raw["raw_response"])
        raw_selected = calls[0]["tool_id"] if len(calls) == 1 else None
        raw_arguments = calls[0]["arguments"] if len(calls) == 1 else None
        raw_selection_correct = len(calls) == 1 and raw_selected in gold["acceptable_tools_development_scope"]
        raw_parameters_correct = gate.mapping_equal(
            (raw_arguments or {}).get("compositions"), gold["expected_parameters"]["compositions"]
        )
        gate_selection_correct = (
            gated["output_tool_call_count"] == 1
            and gated["selected_tool_id"] in gold["acceptable_tools_development_scope"]
        )
        gate_parameters_correct = gate.mapping_equal(
            (gated["selected_arguments"] or {}).get("compositions"),
            gold["expected_parameters"]["compositions"],
        )
        scores.append({
            "task_id": task_id, "raw_tool_call_count": len(calls),
            "raw_called_tool_ids": [row["tool_id"] for row in calls],
            "raw_selection_correct": raw_selection_correct,
            "raw_parameters_correct": raw_parameters_correct,
            "raw_complete_call_correct": raw_selection_correct and raw_parameters_correct,
            "gate_decision": gated["decision"], "gate_selected_tool_id": gated["selected_tool_id"],
            "gate_selection_correct": gate_selection_correct,
            "gate_parameters_correct": gate_parameters_correct,
            "gate_complete_call_correct": gate_selection_correct and gate_parameters_correct,
            "gate_intervened": gated["decision"] != "allow_original_single_call",
            "raw_response_modified": gate_by_id[task_id]["raw_response_modified"],
        })
    latency = [row["api_latency_ms"] for row in raw_rows]
    report = {
        "schema_version": "1.0", "analysis_id": config["analysis_id"],
        "analysis_status": "offline_scoring_complete",
        "task_count": 10, "transport_accepted_count": sum(row["transport_accepted"] for row in raw_rows),
        "raw_exactly_one_call_count": sum(row["raw_tool_call_count"] == 1 for row in scores),
        "raw_structure_violation_count": sum(row["raw_tool_call_count"] != 1 for row in scores),
        "raw_selection_correct_count": sum(row["raw_selection_correct"] for row in scores),
        "raw_parameters_correct_count": sum(row["raw_parameters_correct"] for row in scores),
        "raw_complete_call_correct_count": sum(row["raw_complete_call_correct"] for row in scores),
        "gate_complete_call_correct_count": sum(row["gate_complete_call_correct"] for row in scores),
        "gate_intervention_count": sum(row["gate_intervened"] for row in scores),
        "gate_false_block_count": sum(
            row["raw_complete_call_correct"] and not row["gate_complete_call_correct"] for row in scores
        ),
        "mean_api_latency_ms": mean(latency), "median_api_latency_ms": median(latency),
        "external_api_calls": docs["runtime_report"]["external_api_calls"],
        "tool_calls_executed": docs["runtime_report"]["tool_calls_executed"],
        "retries_executed": docs["runtime_report"]["retries_executed"],
        "raw_responses_modified": False, "causal_gate_benefit_claim_allowed": False,
        "independent_validation_claim_allowed": False, "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress", "core_frozen": False,
        "interpretation": "all ten new probes were already correct single A004 calls; this run tests false-block safety but cannot estimate gate correction benefit",
    }
    return {"scores": scores, "report": report}


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = gate.load_json(CONFIG_PATH)
    result = analyze(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    gate.write_json(output_dir / "a004_postgate_analysis_config_snapshot.json", config)
    gate.write_json(output_dir / "a004_postgate_per_task_scores.json", {
        "schema_version": "1.0", "rows": result["scores"]
    })
    gate.write_json(output_dir / "a004_postgate_analysis_report.json", result["report"])
    artifact_paths = list(output_dir.iterdir())
    gate.write_json(output_dir / "artifact_manifest.json", {
        "schema_version": "1.0", "analysis_id": config["analysis_id"],
        "artifact_count": len(artifact_paths),
        "artifacts": [{"filename": path.name, "sha256": gate.file_hash(path), "bytes": path.stat().st_size}
                      for path in sorted(artifact_paths, key=lambda item: item.name)],
    })
    return result["report"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else gate.WORKSPACE / args.output_dir
    print(json.dumps(build_outputs(output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
