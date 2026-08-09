"""Build the no-call A003 development-routing opening package.

This package freezes a small balanced development grid and keeps scoring gold
separate from router-visible inputs.  It deliberately refuses to open external
execution while any registered routing method lacks a hash-frozen implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "a003_routing_development_config_v1.json"
PROMPT_PATH = HERE / "a003_routing_prompt_v1.json"
EXPECTED_TASK_IDS = ["E1B2-A003-001", "E1B2-A003-002"]
EXPECTED_POOL_SIZES = [17, 120]
EXPECTED_POOL_REPEATS = ["A", "B"]
EXPECTED_CONDITIONS = [
    ("none", 0),
    ("lexical", 8),
    ("functional_overlap", 8),
]
EXPECTED_METHODS = [
    "full_schema",
    "lexical_top5",
    "dense_top5",
    "hierarchical",
]
READY_STATUS = "ready"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def json_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate_binding(binding: dict[str, str]) -> Path:
    path = WORKSPACE / binding["path"]
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256_file(path)
    if actual != binding["sha256"].lower():
        raise ValueError(f"bound file hash mismatch for {path}: {actual}")
    return path


def validate_design(config: dict[str, Any], prompt: dict[str, Any]) -> None:
    if config["selected_task_ids"] != EXPECTED_TASK_IDS:
        raise ValueError("selected_task_ids must remain the strict/loose Fe2O3 pair")
    if config["selected_pool_sizes"] != EXPECTED_POOL_SIZES:
        raise ValueError("selected_pool_sizes must remain the 17/120 endpoints")
    if config["selected_pool_repeats"] != EXPECTED_POOL_REPEATS:
        raise ValueError("selected_pool_repeats must remain A/B")
    observed_conditions = [
        (row["near_neighbor_type"], row["near_neighbor_count"])
        for row in config["selected_conditions"]
    ]
    if observed_conditions != EXPECTED_CONDITIONS:
        raise ValueError("selected_conditions must remain none-0/lexical-8/functional-8")
    if config["methods"] != EXPECTED_METHODS:
        raise ValueError("methods must remain the four preregistered non-Oracle methods")
    if config["top_k"] != 5 or config["model_run_repeats"] != [1]:
        raise ValueError("development opening must remain Top-5 with one model repeat")
    if config["scheduled_cell_count"] != 96:
        raise ValueError("scheduled_cell_count must remain 96")
    for field in (
        "tool_execution_allowed",
        "external_api_calls_authorized",
        "confirmatory_inference_allowed",
        "formal_pool_use_allowed",
        "gold_visible_to_router",
        "independent_validation_split_access_allowed",
        "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")
    if prompt["selector_policy"]["tool_execution_allowed"] is not False:
        raise ValueError("selector prompt must prohibit tool execution")
    if prompt["selector_policy"]["maximum_tool_calls"] != 1:
        raise ValueError("selector prompt must permit at most one tool call")


def selected_tasks(
    config: dict[str, Any],
    taskset: dict[str, Any],
    gold_registry: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    task_by_id = {row["task_id"]: row for row in taskset["tasks"]}
    gold_rows = gold_registry.get("tasks", gold_registry.get("records", []))
    gold_by_id = {row["task_id"]: row for row in gold_rows}
    input_rows = []
    scoring_rows = []
    for task_id in config["selected_task_ids"]:
        task = task_by_id[task_id]
        gold = gold_by_id[task_id]
        if task["source_tool_id"] != config["target_tool_id"]:
            raise ValueError(f"unexpected source tool for {task_id}")
        if task["base_task_group_id"] != "A003-01":
            raise ValueError("development pair must share the Fe2O3 base task")
        input_rows.append(
            {
                "task_id": task_id,
                "task_pair_id": task["task_pair_id"],
                "base_task_group_id": task["base_task_group_id"],
                "precision_policy": task["precision_policy"],
                "problem_text": task["problem_text"],
            }
        )
        scoring_rows.append(
            {
                "task_id": task_id,
                "canonical_inputs": deepcopy(task["canonical_inputs"]),
                "scoring_rule": deepcopy(gold["scoring_rule"]),
                "acceptable_tools": deepcopy(
                    gold["revalidated_primary_acceptable_tools"]
                ),
                "alternative_success_must_be_reported": gold[
                    "alternative_success_must_be_reported"
                ],
            }
        )
    if [row["precision_policy"] for row in input_rows] != [
        "strict_versioned",
        "approximate_educational",
    ]:
        raise ValueError("selected tasks must be a strict/loose precision pair")
    if scoring_rows[0]["acceptable_tools"] != ["A003"]:
        raise ValueError("strict task acceptable-tools set changed")
    if scoring_rows[1]["acceptable_tools"] != ["A003", "E3C004"]:
        raise ValueError("loose task acceptable-tools set changed")
    return (
        {
            "schema_version": "1.0",
            "opening_id": config["opening_id"],
            "router_visible": True,
            "gold_fields_present": False,
            "task_count": len(input_rows),
            "tasks": input_rows,
        },
        {
            "schema_version": "1.0",
            "opening_id": config["opening_id"],
            "router_visible": False,
            "use": "offline_scoring_only",
            "task_count": len(scoring_rows),
            "tasks": scoring_rows,
        },
    )


def selected_pools(
    config: dict[str, Any],
    pool_manifest: dict[str, Any],
    schema_registry: dict[str, Any],
) -> dict[str, Any]:
    schema_by_id = {row["tool_id"]: row for row in schema_registry["entries"]}
    wanted = {
        (size, repeat, neighbor_type, count)
        for size in config["selected_pool_sizes"]
        for repeat in config["selected_pool_repeats"]
        for neighbor_type, count in EXPECTED_CONDITIONS
    }
    rows = [
        row
        for row in pool_manifest["records"]
        if (
            row["tool_pool_size"],
            row["pool_repeat"],
            row["near_neighbor_type"],
            row["near_neighbor_count"],
        )
        in wanted
    ]
    if len(rows) != 12:
        raise ValueError(f"expected 12 selected pools, found {len(rows)}")
    observed = {
        (
            row["tool_pool_size"],
            row["pool_repeat"],
            row["near_neighbor_type"],
            row["near_neighbor_count"],
        )
        for row in rows
    }
    if observed != wanted:
        raise ValueError("selected pool grid is incomplete")
    output_rows = []
    for row in rows:
        if len(row["tool_order"]) != row["tool_pool_size"]:
            raise ValueError(f"pool size mismatch: {row['pool_id']}")
        if len(set(row["tool_order"])) != len(row["tool_order"]):
            raise ValueError(f"duplicate tool in pool: {row['pool_id']}")
        if config["target_tool_id"] not in row["tool_order"]:
            raise ValueError(f"target absent from pool: {row['pool_id']}")
        missing = [tool_id for tool_id in row["tool_order"] if tool_id not in schema_by_id]
        if missing:
            raise ValueError(f"schemas absent from registry: {missing}")
        schema_view = [schema_by_id[tool_id]["openai_tool"] for tool_id in row["tool_order"]]
        output_rows.append(
            {
                "pool_id": row["pool_id"],
                "tool_pool_size": row["tool_pool_size"],
                "pool_repeat": row["pool_repeat"],
                "near_neighbor_type": row["near_neighbor_type"],
                "near_neighbor_count": row["near_neighbor_count"],
                "evidence_relation_type": row["evidence_relation_type"],
                "functional_overlap_operationalization": row[
                    "functional_overlap_operationalization"
                ],
                "confirmatory_use_allowed": row["confirmatory_use_allowed"],
                "tool_order": deepcopy(row["tool_order"]),
                "tool_order_sha256": json_hash(row["tool_order"]),
                "full_schema_view_sha256": json_hash(schema_view),
            }
        )
    output_rows.sort(
        key=lambda row: (
            row["tool_pool_size"],
            row["pool_repeat"],
            EXPECTED_CONDITIONS.index(
                (row["near_neighbor_type"], row["near_neighbor_count"])
            ),
        )
    )
    return {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "pool_count": len(output_rows),
        "schema_registry_sha256": config["bindings"]["pool_schema_registry"]["sha256"],
        "pools": output_rows,
    }


def method_readiness(
    config: dict[str, Any],
    cf06_report: dict[str, Any],
) -> dict[str, Any]:
    cf06_sizes = {
        row["tool_count"]: row for row in cf06_report["size_results"]
    }
    full_schema_ready = all(
        cf06_sizes[size]["auto_request_accepted"]
        and cf06_sizes[size]["native_function_call_returned"]
        for size in EXPECTED_POOL_SIZES
    )
    rows = []
    for method in config["methods"]:
        declared = config["method_readiness_policy"][method]
        status = declared["implementation_status"]
        if method == "full_schema" and not full_schema_ready:
            status = "blocked_cf06_endpoint_failure"
        rows.append(
            {
                "method": method,
                "top_k": None if method == "full_schema" else config["top_k"],
                "implementation_status": status,
                "ready_for_external_development_run": status == READY_STATUS,
                "basis": declared["basis"],
                "required_runtime_output": (
                    None
                    if method == "full_schema"
                    else [
                        "ordered_candidate_tool_ids",
                        "retrieval_scores",
                        "retrieval_latency_ms",
                        "retriever_config_sha256",
                    ]
                ),
            }
        )
    ready_count = sum(row["ready_for_external_development_run"] for row in rows)
    return {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "required_method_count": len(rows),
        "ready_method_count": ready_count,
        "all_methods_ready": ready_count == len(rows),
        "external_execution_gate_open": False,
        "methods": rows,
        "next_gate": (
            "implement and hash-freeze lexical_top5, dense_top5, and hierarchical; "
            "then rebuild this package before requesting external execution authorization"
        ),
    }


def run_cells(
    config: dict[str, Any],
    input_tasks: dict[str, Any],
    pools: dict[str, Any],
    prompt: dict[str, Any],
) -> dict[str, Any]:
    rows = []
    for task in input_tasks["tasks"]:
        for pool in pools["pools"]:
            for method in config["methods"]:
                for run_repeat in config["model_run_repeats"]:
                    cell_id = (
                        f"A003-DEV-{task['task_id']}-{pool['pool_id']}-"
                        f"{method.upper().replace('_', '-')}-R{run_repeat}"
                    )
                    rows.append(
                        {
                            "cell_id": cell_id,
                            "task_id": task["task_id"],
                            "task_pair_id": task["task_pair_id"],
                            "precision_policy": task["precision_policy"],
                            "pool_id": pool["pool_id"],
                            "tool_pool_size": pool["tool_pool_size"],
                            "pool_repeat": pool["pool_repeat"],
                            "near_neighbor_type": pool["near_neighbor_type"],
                            "near_neighbor_count": pool["near_neighbor_count"],
                            "method": method,
                            "retrieval_required": method != "full_schema",
                            "selector_schema_count": (
                                pool["tool_pool_size"]
                                if method == "full_schema"
                                else config["top_k"]
                            ),
                            "model_run_repeat": run_repeat,
                            "prompt_id": prompt["prompt_id"],
                            "tool_execution_allowed": False,
                            "gold_visible_to_router": False,
                            "execution_status": "not_executed",
                        }
                    )
    if len(rows) != config["scheduled_cell_count"]:
        raise ValueError("constructed cell count does not match frozen schedule")
    if len({row["cell_id"] for row in rows}) != len(rows):
        raise ValueError("run cell IDs are not unique")
    return {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "development_only": True,
        "request_payloads_materialized": False,
        "external_api_calls": 0,
        "cell_count": len(rows),
        "cells": rows,
    }


def build(config: dict[str, Any], prompt: dict[str, Any]) -> dict[str, Any]:
    validate_design(config, prompt)
    paths = {
        name: validate_binding(binding)
        for name, binding in config["bindings"].items()
    }
    task_revalidation = load_json(paths["task_gold_revalidation_report"])
    if not task_revalidation["development_routing_run_allowed"]:
        raise ValueError("A003 task-gold revalidation does not permit development routing")
    if task_revalidation["confirmatory_use_allowed"]:
        raise ValueError("development opening must not consume confirmatory task gold")

    input_tasks, scoring = selected_tasks(
        config,
        load_json(paths["taskset"]),
        load_json(paths["acceptable_tools_registry"]),
    )
    pools = selected_pools(
        config,
        load_json(paths["controlled_pool_manifest"]),
        load_json(paths["pool_schema_registry"]),
    )
    readiness = method_readiness(config, load_json(paths["cf06_runtime_report"]))
    cells = run_cells(config, input_tasks, pools, prompt)
    cells_text = canonical_json(cells)
    forbidden = set(prompt["gold_fields_forbidden"])
    gold_fields_absent = all(f'"{field}"' not in cells_text for field in forbidden)
    no_api_key = "api_key" not in cells_text.casefold() and "api_key" not in canonical_json(config).casefold()

    counts_by_method = {
        method: sum(row["method"] == method for row in cells["cells"])
        for method in config["methods"]
    }
    counts_by_condition = {
        f"{neighbor_type}-{count}": sum(
            row["near_neighbor_type"] == neighbor_type
            and row["near_neighbor_count"] == count
            for row in cells["cells"]
        )
        for neighbor_type, count in EXPECTED_CONDITIONS
    }
    preflight = {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "opening_status": "prepared_blocked_pending_method_implementation",
        "design": {
            "task_count": input_tasks["task_count"],
            "pool_count": pools["pool_count"],
            "method_count": len(config["methods"]),
            "model_run_repeat_count": len(config["model_run_repeats"]),
            "cell_count": cells["cell_count"],
            "counts_by_method": counts_by_method,
            "counts_by_condition": counts_by_condition,
        },
        "checks": {
            "all_bound_hashes_valid": True,
            "strict_loose_task_pair_valid": True,
            "pool_grid_complete": pools["pool_count"] == 12,
            "cell_grid_complete": cells["cell_count"] == 96,
            "gold_fields_absent_from_run_cells": gold_fields_absent,
            "api_key_absent": no_api_key,
            "tool_execution_disabled": True,
            "external_api_calls_zero": True,
            "all_methods_ready": readiness["all_methods_ready"],
        },
        "external_api_calls": 0,
        "tool_calls_executed": 0,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
    }
    if not all(
        value
        for key, value in preflight["checks"].items()
        if key != "all_methods_ready"
    ):
        raise ValueError("offline opening preflight failed")

    return {
        "input_tasks": input_tasks,
        "scoring_registry": scoring,
        "selected_pools": pools,
        "method_readiness": readiness,
        "run_cells": cells,
        "preflight": preflight,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    prompt = load_json(PROMPT_PATH)
    authorization_path = HERE / config["execution_authorization_file"]
    if authorization_path.exists():
        raise ValueError("unexpected A003 routing execution authorization file")
    built = build(config, prompt)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a003_routing_development_config_snapshot.json": config,
        "a003_routing_prompt_snapshot.json": prompt,
        "a003_routing_input_tasks.json": built["input_tasks"],
        "a003_routing_scoring_registry.json": built["scoring_registry"],
        "a003_routing_selected_pools.json": built["selected_pools"],
        "a003_routing_method_readiness.json": built["method_readiness"],
        "a003_routing_run_cells.json": built["run_cells"],
        "a003_routing_opening_preflight.json": built["preflight"],
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    authorization_request = {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "decision": "pending_not_eligible",
        "eligible_for_external_execution_authorization": False,
        "blocking_reason": "three preregistered routing methods lack hash-frozen implementations",
        "required_before_authorization": [
            "lexical_top5 implementation passes the bound 120-tool registry tests",
            "dense_top5 implementation and embedding snapshot are hash-frozen",
            "hierarchical implementation and taxonomy/config are hash-frozen",
            "all four methods produce deterministic candidate views on the 96-cell opening grid",
            "a separate user authorization explicitly approves sending the frozen inputs and schemas",
        ],
        "external_data_sharing_authorized": False,
        "external_api_execution_authorized": False,
        "tool_execution_allowed": False,
        "request_payloads_materialized": False,
        "bindings": {
            filename: sha256_file(output_dir / filename)
            for filename in sorted(artifacts)
        },
    }
    write_json(output_dir / "execution_authorization_request.json", authorization_request)
    artifact_rows = []
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name):
        if path.name == "artifact_manifest.json" or not path.is_file():
            continue
        artifact_rows.append(
            {
                "filename": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    manifest = {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "artifact_count": len(artifact_rows),
        "artifacts": artifact_rows,
    }
    write_json(output_dir / "artifact_manifest.json", manifest)
    return built["preflight"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = WORKSPACE / output_dir
    report = build_outputs(output_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
