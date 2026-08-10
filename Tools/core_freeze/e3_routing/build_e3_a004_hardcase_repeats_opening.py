"""Build the unexecuted R2/R3 repeat package for the A004 hard-case run."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("a004_hardcase_repeats_opening_config_v1.json")
EXPECTED_METHODS = ["full_schema", "lexical_top5", "dense_top5", "hierarchical"]
EXPECTED_CONDITIONS = ["none_0", "lexical_4", "contract_mismatch_4"]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_binding(binding: dict[str, str]) -> Path:
    path = WORKSPACE / binding["path"]
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = file_hash(path)
    if actual != binding["sha256"].lower():
        raise ValueError(f"bound file hash mismatch for {path}: {actual}")
    return path


def validate_config(config: dict[str, Any]) -> None:
    if config["model_run_repeats"] != [2, 3] or config["base_cell_count"] != 48:
        raise ValueError("repeat plan must remain R2/R3 over 48 base cells")
    if config["scheduled_request_count"] != 96 or config["provider_attempts_per_cell"] != 1:
        raise ValueError("repeat plan must remain 96 one-attempt requests")
    if config["task_schema_prompt_retrieval_scoring_changes_allowed"] is not False:
        raise ValueError("R2/R3 cannot change frozen inputs or scoring")
    if config["request_order_reordering_allowed"] is not False:
        raise ValueError("R2/R3 must preserve R1 cell order")
    for field in ("tool_execution_allowed", "provider_retry_allowed", "external_api_calls_authorized",
                  "independent_validation_split_access_allowed", "confirmatory_inference_allowed",
                  "core_frozen"):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")


def validate_source_artifacts(config: dict[str, Any], docs: dict[str, Any]) -> dict[str, Any]:
    cells = docs["r1_run_cells"]["cells"]
    tasks = docs["input_tasks"]["tasks"]
    views = docs["candidate_views"]["views"]
    results = docs["r1_request_results"]["results"]
    scored = docs["r1_scored_rows"]["rows"]
    report = docs["r1_overall_report"]
    if len(tasks) != 2 or len(views) != 42 or len(cells) != 48:
        raise ValueError("source opening dimensions changed")
    if len(results) != 48 or len(scored) != 48 or report["failure_count"] != 1:
        raise ValueError("R1 evidence dimensions changed")
    cell_ids = [row["cell_id"] for row in cells]
    if [row["cell_id"] for row in results] != cell_ids:
        raise ValueError("R1 result order differs from frozen cell order")
    if {row["cell_id"] for row in scored} != set(cell_ids):
        raise ValueError("R1 scoring coverage differs from frozen cells")
    if any(row["model_run_repeat"] != 1 or not row["cell_id"].endswith("-R1") for row in cells):
        raise ValueError("source cells are not R1 cells")
    if docs["source_opening_manifest"]["artifact_count"] != 12:
        raise ValueError("source opening manifest changed")
    if docs["r1_runtime_manifest"]["artifact_count"] != 5:
        raise ValueError("R1 runtime manifest changed")
    if docs["r1_analysis_manifest"]["artifact_count"] != 9:
        raise ValueError("R1 analysis manifest changed")
    return {"tasks": tasks, "views": views, "cells": cells, "results": results,
            "scored": scored, "prompt": docs["selector_prompt"],
            "scoring": docs["scoring_registry"]}


def build_repeat_cells(config: dict[str, Any], r1_cells: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for repeat in config["model_run_repeats"]:
        run_id = config["planned_run_ids"][repeat - 2]
        for source in r1_cells:
            row = deepcopy(source)
            row["parent_r1_cell_id"] = source["cell_id"]
            row["cell_id"] = source["cell_id"][:-2] + f"R{repeat}"
            row["model_run_repeat"] = repeat
            row["planned_run_id"] = run_id
            row["execution_status"] = "not_executed"
            rows.append(row)
    if len(rows) != 96 or len({row["cell_id"] for row in rows}) != 96:
        raise ValueError("repeat cell grid is incomplete")
    for repeat in (2, 3):
        subset = [row for row in rows if row["model_run_repeat"] == repeat]
        if len(subset) != 48:
            raise ValueError(f"R{repeat} cell count changed")
        if [row["parent_r1_cell_id"] for row in subset] != [row["cell_id"] for row in r1_cells]:
            raise ValueError(f"R{repeat} cell order differs from R1")
    return {"schema_version": "1.0", "opening_id": config["opening_id"],
            "request_payloads_materialized": False, "external_api_calls": 0,
            "cell_count": 96, "cells": rows}


def build_pairing_plan(config: dict[str, Any], r1_cells: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for cell in r1_cells:
        base = cell["cell_id"][:-2]
        rows.append({
            "pairing_unit_id": f"PAIR-{base.rstrip('-')}",
            "task_id": cell["task_id"], "condition_id": cell["condition_id"],
            "near_neighbor_type": cell["near_neighbor_type"], "near_neighbor_count": cell["near_neighbor_count"],
            "tool_pool_size": cell["tool_pool_size"], "method": cell["method"],
            "candidate_view_id": cell["candidate_view_id"],
            "r1_cell_id": cell["cell_id"], "r2_cell_id": base + "R2", "r3_cell_id": base + "R3",
            "same_task_schema_prompt_retrieval_scoring_required": True,
        })
    return {"schema_version": "1.0", "opening_id": config["opening_id"],
            "pairing_unit_count": 48, "repeats_per_unit": 3, "rows": rows}


def volatility_contract(config: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    r1_failures = [row for row in source["scored"] if not row["complete_call_correct"]]
    return {
        "schema_version": "1.0", "contract_id": "A004-HARDCASE-REPEAT-VOLATILITY-V1",
        "analysis_unit": "task_id_x_condition_id_x_tool_pool_size_x_method",
        "repeat_ids": [1, 2, 3], "primary_development_outcome": "complete_call_correct",
        "secondary_outcomes": ["exactly_one_tool_call", "selection_correct", "parameters_correct", "tool_call_count"],
        "classification": {
            "stable_correct": "3_of_3_complete_call_correct",
            "intermittent": "1_or_2_of_3_complete_call_correct",
            "stable_failure": "0_of_3_complete_call_correct"
        },
        "required_outputs": [
            "per_pair_repeat_outcomes", "exact_three_repeat_agreement_rate", "failure_frequency_per_pair",
            "summary_by_condition", "summary_by_method", "summary_by_tool_pool_size",
            "r1_failure_recurrence_audit"
        ],
        "r1_observed_failure_count": len(r1_failures),
        "r1_observed_failure_cell_ids": [row["cell_id"] for row in r1_failures],
        "r1_result_used_only_to_motivate_identical_repeats": True,
        "inputs_or_scoring_tuned_after_r1": False,
        "majority_vote_replaces_gold": False,
        "significance_testing_allowed": False,
        "confirmatory_inference_allowed": False,
    }


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {name: validate_binding(binding) for name, binding in config["bindings"].items()}
    docs = {name: load_json(path) for name, path in paths.items()}
    source = validate_source_artifacts(config, docs)
    cells = build_repeat_cells(config, source["cells"])
    pairs = build_pairing_plan(config, source["cells"])
    contract = volatility_contract(config, source)
    public_text = canonical_json({"tasks": docs["input_tasks"], "views": docs["candidate_views"], "cells": cells})
    gold_absent = all(f'"{field}"' not in public_text for field in source["prompt"]["gold_fields_forbidden"])
    checks = {
        "all_bound_hashes_valid": True,
        "source_opening_and_r1_evidence_complete": True,
        "r2_cell_count_48": sum(row["model_run_repeat"] == 2 for row in cells["cells"]) == 48,
        "r3_cell_count_48": sum(row["model_run_repeat"] == 3 for row in cells["cells"]) == 48,
        "r1_order_preserved_in_each_repeat": True,
        "task_schema_prompt_retrieval_scoring_unchanged": True,
        "pairing_plan_complete_48_units": pairs["pairing_unit_count"] == 48,
        "router_visible_artifacts_exclude_gold_fields": gold_absent,
        "request_payloads_not_materialized": cells["request_payloads_materialized"] is False,
        "external_api_calls_zero": True,
        "tool_execution_zero": True,
        "independent_validation_access_zero": True,
        "confirmatory_inference_disabled": True,
    }
    if not all(checks.values()):
        raise ValueError("repeat opening preflight failed")
    preflight = {
        "schema_version": "1.0", "opening_id": config["opening_id"],
        "opening_status": "prepared_local_gate_passed_pending_external_authorization",
        "design": {"base_cell_count": 48, "new_repeat_count": 2, "scheduled_request_count": 96,
                   "three_repeat_pairing_unit_count": 48},
        "checks": checks, "external_api_calls": 0, "tool_calls_executed": 0,
        "independent_validation_split_accessed": False, "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress", "core_frozen": False,
    }
    return {"input_tasks": docs["input_tasks"], "candidate_views": docs["candidate_views"],
            "selector_prompt": docs["selector_prompt"], "scoring_registry": docs["scoring_registry"],
            "repeat_cells": cells, "pairing_plan": pairs, "volatility_contract": contract,
            "preflight": preflight}


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    built = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a004_repeats_config_snapshot.json": config,
        "a004_repeats_input_tasks_snapshot.json": built["input_tasks"],
        "a004_repeats_candidate_views_snapshot.json": built["candidate_views"],
        "a004_repeats_selector_prompt_snapshot.json": built["selector_prompt"],
        "a004_repeats_scoring_registry_snapshot.json": built["scoring_registry"],
        "a004_repeats_run_cells.json": built["repeat_cells"],
        "a004_three_repeat_pairing_plan.json": built["pairing_plan"],
        "a004_repeat_volatility_contract.json": built["volatility_contract"],
        "a004_repeats_opening_preflight.json": built["preflight"],
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    authorization = {
        "schema_version": "1.0", "opening_id": config["opening_id"],
        "decision": "pending_user_authorization",
        "eligible_for_external_execution_authorization": True,
        "external_data_sharing_authorized": False,
        "external_api_execution_authorized": False,
        "provider_retry_authorized": False,
        "tool_execution_allowed": False,
        "independent_validation_split_access_allowed": False,
        "request_payloads_materialized": False,
        "required_scope_if_authorized": "same 48 frozen A004 cells repeated as R2 and R3; 96 one-shot DeepSeek requests; no input, schema, prompt, retrieval, or scoring changes; no tool execution; no independent validation access",
        "bindings": {name: file_hash(output_dir / name) for name in sorted(artifacts)},
    }
    write_json(output_dir / "execution_authorization_request.json", authorization)
    rows = []
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name):
        if path.is_file() and path.name != "artifact_manifest.json":
            rows.append({"filename": path.name, "sha256": file_hash(path), "bytes": path.stat().st_size})
    write_json(output_dir / "artifact_manifest.json", {"schema_version": "1.0", "opening_id": config["opening_id"],
               "artifact_count": len(rows), "artifacts": rows})
    return built["preflight"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else WORKSPACE / args.output_dir
    print(json.dumps(build_outputs(output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
