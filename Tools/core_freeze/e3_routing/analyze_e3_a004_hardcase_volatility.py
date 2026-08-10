"""Offline three-repeat volatility analysis for the A004 hard-case slice."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing import analyze_e3_a004_hardcase_development as base


WORKSPACE = base.WORKSPACE
CONFIG_PATH = Path(__file__).with_name("a004_hardcase_volatility_analysis_config_v1.json")
load_json = base.load_json
write_json = base.write_json
file_hash = base.file_hash
summarize = base.summarize
grouped = base.grouped
parameters_compatible = base.parameters_compatible


def validate_binding(binding: dict[str, str]) -> Path:
    path = WORKSPACE / binding["path"]
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = file_hash(path)
    if actual != binding["sha256"].lower():
        raise ValueError(f"bound file hash mismatch for {path}: {actual}")
    return path


def validate_config(config: dict[str, Any]) -> None:
    if config["model_run_repeats"] != [1, 2, 3]:
        raise ValueError("volatility analysis must use R1/R2/R3")
    if config["expected_pairing_unit_count"] != 48 or config["expected_repeat_result_count"] != 96 or config["expected_all_result_count"] != 144:
        raise ValueError("volatility analysis dimensions changed")
    if config["development_only"] is not True:
        raise ValueError("analysis must remain development-only")
    for field in ("significance_testing_allowed", "confirmatory_inference_allowed", "core_frozen"):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")


def called_tool_ids(raw_response: Any) -> list[str]:
    if not isinstance(raw_response, dict) or not raw_response.get("choices"):
        return []
    message = raw_response["choices"][0].get("message", {})
    calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
    return [call.get("function", {}).get("name") for call in calls]


def score_repeat_rows(results: list[dict[str, Any]], scoring: dict[str, Any],
                      candidate_views: dict[str, Any]) -> list[dict[str, Any]]:
    gold_by_task = {row["task_id"]: row for row in scoring["tasks"]}
    schemas_by_view = {
        view["candidate_view_id"]: {tool["function"]["name"]: tool["function"]["parameters"]
                                    for tool in view["openai_tools"]}
        for view in candidate_views["views"]
    }
    rows = []
    for result in results:
        gold = gold_by_task[result["task_id"]]
        visible = set(result["selected_schema_tool_ids"])
        if "A004" not in visible:
            raise ValueError(f"A004 absent from repeat view: {result['cell_id']}")
        selected_visible = result["selected_tool_id"] in visible
        selection_correct = bool(result["transport_accepted"] and result["exactly_one_tool_call"]
                                 and selected_visible and result["selected_tool_id"] == "A004")
        selected_schema = schemas_by_view.get(result["candidate_view_id"], {}).get(result["selected_tool_id"])
        parameters_correct = bool(result["exactly_one_tool_call"] and isinstance(selected_schema, dict)
                                  and result["arguments_json_valid"]
                                  and parameters_compatible(result["arguments"], gold["expected_parameters"], selected_schema))
        rows.append({
            "cell_id": result["cell_id"], "parent_r1_cell_id": result["parent_r1_cell_id"],
            "model_run_repeat": result["model_run_repeat"], "task_id": result["task_id"],
            "target_tool_id": "A004", "condition_id": result["condition_id"],
            "near_neighbor_type": result["near_neighbor_type"], "near_neighbor_count": result["near_neighbor_count"],
            "tool_pool_size": result["tool_pool_size"], "method": result["method"],
            "candidate_view_id": result["candidate_view_id"], "transport_accepted": result["transport_accepted"],
            "tool_call_count": result["tool_call_count"], "called_tool_ids": called_tool_ids(result["raw_response"]),
            "exactly_one_tool_call": result["exactly_one_tool_call"], "selected_tool_id": result["selected_tool_id"],
            "selected_tool_visible": selected_visible, "selection_correct": selection_correct,
            "arguments": result["arguments"], "expected_parameters": gold["expected_parameters"],
            "parameters_correct": parameters_correct, "complete_call_correct": selection_correct and parameters_correct,
            "api_latency_ms": result["api_latency_ms"], "usage": result["usage"],
            "tool_executed": result["tool_executed"], "retry_count": result["retry_count"],
        })
    return rows


def enrich_r1_rows(scored: list[dict[str, Any]], raw_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_by_id = {row["cell_id"]: row for row in raw_results}
    rows = []
    for source in scored:
        row = deepcopy(source)
        raw = raw_by_id[row["cell_id"]]
        row["parent_r1_cell_id"] = row["cell_id"]
        row["model_run_repeat"] = 1
        row["called_tool_ids"] = called_tool_ids(raw["raw_response"])
        row["tool_call_count"] = raw["tool_call_count"]
        rows.append(row)
    return rows


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {name: validate_binding(binding) for name, binding in config["bindings"].items()}
    docs = {name: load_json(path) for name, path in paths.items()}
    repeat_results = docs["repeat_request_results"]["results"]
    runtime = docs["repeat_runtime_report"]
    if len(repeat_results) != 96 or Counter(row["model_run_repeat"] for row in repeat_results) != Counter({2: 48, 3: 48}):
        raise ValueError("R2/R3 result grid changed")
    if runtime["external_api_calls"] != 96 or runtime["transport_accepted_count"] != 96 or runtime["provider_error_count"] != 0:
        raise ValueError("R2/R3 transport contract failed")
    if runtime["tool_calls_executed"] != 0 or runtime["retries_executed"] != 0 or runtime["independent_validation_split_accessed"] is not False:
        raise ValueError("R2/R3 safety contract failed")
    repeat_scored = score_repeat_rows(repeat_results, docs["scoring_registry"], docs["candidate_views"])
    r1_scored = enrich_r1_rows(docs["r1_scored_rows"]["rows"], docs["r1_request_results"]["results"])
    all_rows = r1_scored + repeat_scored
    if len(all_rows) != 144 or Counter(row["model_run_repeat"] for row in all_rows) != Counter({1: 48, 2: 48, 3: 48}):
        raise ValueError("three-repeat scored grid changed")
    row_by_id = {row["cell_id"]: row for row in all_rows}
    pair_rows = []
    for pair in docs["pairing_plan"]["rows"]:
        ids = [pair["r1_cell_id"], pair["r2_cell_id"], pair["r3_cell_id"]]
        members = [row_by_id[cell_id] for cell_id in ids]
        outcomes = [row["complete_call_correct"] for row in members]
        correct_count = sum(outcomes)
        classification = "stable_correct" if correct_count == 3 else "stable_failure" if correct_count == 0 else "intermittent"
        pair_rows.append({
            "pairing_unit_id": pair["pairing_unit_id"], "task_id": pair["task_id"],
            "condition_id": pair["condition_id"], "near_neighbor_type": pair["near_neighbor_type"],
            "near_neighbor_count": pair["near_neighbor_count"], "tool_pool_size": pair["tool_pool_size"],
            "method": pair["method"], "candidate_view_id": pair["candidate_view_id"],
            "cell_ids": ids, "complete_call_correct_by_repeat": outcomes,
            "complete_call_correct_count": correct_count, "failure_frequency": (3 - correct_count) / 3,
            "exact_three_repeat_agreement": len(set(outcomes)) == 1,
            "classification": classification,
            "tool_call_count_by_repeat": [row["tool_call_count"] for row in members],
            "called_tool_ids_by_repeat": [row["called_tool_ids"] for row in members],
        })
    if len(pair_rows) != 48:
        raise ValueError("pairing output count changed")
    class_counts = Counter(row["classification"] for row in pair_rows)
    pairing_summary = {
        "pairing_unit_count": 48,
        "stable_correct_count": class_counts["stable_correct"],
        "intermittent_count": class_counts["intermittent"],
        "stable_failure_count": class_counts["stable_failure"],
        "exact_three_repeat_agreement_count": sum(row["exact_three_repeat_agreement"] for row in pair_rows),
        "exact_three_repeat_agreement_rate": sum(row["exact_three_repeat_agreement"] for row in pair_rows) / 48,
    }
    by_repeat = grouped(all_rows, lambda row: (row["model_run_repeat"],), ("model_run_repeat",))
    by_condition = grouped(all_rows, lambda row: (row["condition_id"],), ("condition_id",))
    by_method = grouped(all_rows, lambda row: (row["method"],), ("method",))
    by_size = grouped(all_rows, lambda row: (row["tool_pool_size"],), ("tool_pool_size",))
    by_condition_method_size = grouped(
        all_rows, lambda row: (row["condition_id"], row["method"], row["tool_pool_size"]),
        ("condition_id", "method", "tool_pool_size"))
    r1_failure_ids = docs["volatility_contract"]["r1_observed_failure_cell_ids"]
    target_pair = next(row for row in pair_rows if row["cell_ids"][0] in r1_failure_ids)
    recurrence = {
        "r1_failure_cell_id": target_pair["cell_ids"][0],
        "r2_failure_recurred": target_pair["complete_call_correct_by_repeat"][1] is False,
        "r3_failure_recurred": target_pair["complete_call_correct_by_repeat"][2] is False,
        "classification": target_pair["classification"],
        "tool_call_count_by_repeat": target_pair["tool_call_count_by_repeat"],
        "called_tool_ids_by_repeat": target_pair["called_tool_ids_by_repeat"],
        "exact_same_called_tool_sequence_all_repeats": len({tuple(x) for x in target_pair["called_tool_ids_by_repeat"]}) == 1,
    }
    report = {
        "schema_version": "1.0", "analysis_id": config["analysis_id"],
        "analysis_status": "three_repeat_development_volatility_analysis_complete",
        "all_repeat_cell_count": 144, "overall": summarize(all_rows),
        "pairing_summary": pairing_summary, "r1_failure_recurrence": recurrence,
        "tool_calls_executed": 0, "retries_executed": 0,
        "independent_validation_split_accessed": False,
        "significance_testing_performed": False, "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress", "core_frozen": False,
        "interpretation": "development evidence of a reproducible local failure; not a confirmatory H3 or H4 result",
    }
    return {"repeat_scored": repeat_scored, "all_rows": all_rows, "pair_rows": pair_rows,
            "pairing_summary": pairing_summary, "by_repeat": by_repeat, "by_condition": by_condition,
            "by_method": by_method, "by_size": by_size,
            "by_condition_method_size": by_condition_method_size,
            "recurrence": recurrence, "report": report}


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    built = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a004_volatility_analysis_config_snapshot.json": config,
        "a004_r2r3_scored_rows.json": {"schema_version": "1.0", "rows": built["repeat_scored"]},
        "a004_all_three_repeat_scored_rows.json": {"schema_version": "1.0", "rows": built["all_rows"]},
        "a004_per_pair_repeat_outcomes.json": {"schema_version": "1.0", "rows": built["pair_rows"]},
        "a004_pairing_summary.json": built["pairing_summary"],
        "a004_by_repeat.json": built["by_repeat"],
        "a004_by_condition_three_repeats.json": built["by_condition"],
        "a004_by_method_three_repeats.json": built["by_method"],
        "a004_by_size_three_repeats.json": built["by_size"],
        "a004_by_condition_method_size_three_repeats.json": built["by_condition_method_size"],
        "a004_r1_failure_recurrence.json": built["recurrence"],
        "a004_three_repeat_overall_report.json": built["report"],
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    rows = [{"filename": path.name, "sha256": file_hash(path), "bytes": path.stat().st_size}
            for path in sorted(output_dir.iterdir(), key=lambda item: item.name)]
    write_json(output_dir / "artifact_manifest.json", {"schema_version": "1.0", "analysis_id": config["analysis_id"],
               "artifact_count": len(rows), "artifacts": rows})
    return built["report"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else WORKSPACE / args.output_dir
    print(json.dumps(build_outputs(output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
