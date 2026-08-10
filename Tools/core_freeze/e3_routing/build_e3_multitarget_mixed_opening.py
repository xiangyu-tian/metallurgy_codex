"""Build the offline 17/120 mixed-realistic E3 multi-target opening package."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing.hierarchical_top5_router import ContractHierarchyTop5
from Tools.core_freeze.e3_routing.lexical_top5_router import WeightedUnicodeNgramBM25


WORKSPACE = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "multitarget_mixed_opening_config_v1.json"
PROMPT_PATH = HERE / "multitarget_routing_prompt_v1.json"
EXPECTED_TARGETS = ["A001", "A002", "A004", "B019"]
EXPECTED_POOL_SIZES = [17, 120]
EXPECTED_METHODS = ["full_schema", "lexical_top5", "dense_top5", "hierarchical"]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_binding(binding: dict[str, str]) -> Path:
    path = WORKSPACE / binding["path"]
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256_file(path)
    if actual != binding["sha256"].lower():
        raise ValueError(f"bound file hash mismatch for {path}: {actual}")
    return path


def validate_design(config: dict[str, Any], prompt: dict[str, Any]) -> None:
    if config["selected_pool_sizes"] != EXPECTED_POOL_SIZES:
        raise ValueError("selected_pool_sizes must remain [17, 120]")
    if config["methods"] != EXPECTED_METHODS:
        raise ValueError("methods must remain the four non-Oracle methods")
    if config["top_k"] != 5 or config["model_run_repeats"] != [1]:
        raise ValueError("opening must remain Top-5 with one model repeat")
    if config["scheduled_cell_count"] != 64 or config["expected_candidate_view_count"] != 50:
        raise ValueError("opening must remain the frozen 64-cell/50-view slice")
    if len(config["selected_task_ids"]) != 8:
        raise ValueError("opening must contain exactly eight tasks")
    for field in (
        "tool_execution_allowed",
        "external_api_calls_authorized",
        "confirmatory_inference_allowed",
        "formal_pool_use_allowed",
        "gold_visible_to_router",
        "independent_validation_split_access_allowed",
        "full_137_registry_gold_claim_allowed",
        "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")
    if prompt["selector_policy"]["tool_execution_allowed"] is not False:
        raise ValueError("prompt must prohibit tool execution")
    if prompt["selector_policy"]["maximum_tool_calls"] != 1:
        raise ValueError("prompt must allow at most one tool call")


def selected_tasks(
    config: dict[str, Any],
    taskset: dict[str, Any],
    gold_registry: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    task_by_id = {row["task_id"]: row for row in taskset["tasks"]}
    gold_by_id = {row["task_id"]: row for row in gold_registry["tasks"]}
    input_rows = []
    scoring_rows = []
    for task_id in config["selected_task_ids"]:
        task = task_by_id[task_id]
        gold = gold_by_id[task_id]
        if task["source_tool_id"] not in EXPECTED_TARGETS:
            raise ValueError(f"unexpected target for {task_id}")
        input_rows.append(
            {
                "task_id": task_id,
                "task_family_id": task["task_family_id"],
                "task_pair_id": task["task_pair_id"],
                "base_task_group_id": task["base_task_group_id"],
                "precision_policy": task["precision_policy"],
                "problem_text": task["problem_text"],
            }
        )
        scoring_rows.append(
            {
                "task_id": task_id,
                "source_tool_id": task["source_tool_id"],
                "canonical_inputs": deepcopy(task["canonical_inputs"]),
                "expected_parameters": deepcopy(task["expected_parameters"]),
                "scoring_rule": deepcopy(gold["scoring_rule"]),
                "acceptable_tools_full_candidate_scope": deepcopy(
                    gold["revalidated_primary_acceptable_tools"]
                ),
            }
        )
    counts = {
        target: sum(row["source_tool_id"] == target for row in scoring_rows)
        for target in EXPECTED_TARGETS
    }
    if any(value != 2 for value in counts.values()):
        raise ValueError(f"task allocation must be two per target: {counts}")
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
    manifest: dict[str, Any],
    entry_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    pool_by_size = {row["tool_count"]: row for row in manifest["pools"]}
    rows = []
    for size in config["selected_pool_sizes"]:
        pool = pool_by_size[size]
        tool_ids = pool["tool_ids"]
        if len(tool_ids) != size or len(set(tool_ids)) != size:
            raise ValueError(f"invalid base pool at size {size}")
        if not set(EXPECTED_TARGETS).issubset(tool_ids):
            raise ValueError(f"verified targets absent from size {size}")
        missing = [tool_id for tool_id in tool_ids if tool_id not in entry_by_id]
        if missing:
            raise ValueError(f"catalog schemas missing: {missing}")
        schema_view = [entry_by_id[tool_id]["openai_tool"] for tool_id in tool_ids]
        rows.append(
            {
                "pool_id": pool["pool_id"],
                "pool_design": "mixed_realistic",
                "tool_pool_size": size,
                "tool_order": deepcopy(tool_ids),
                "tool_order_sha256": json_hash(tool_ids),
                "full_schema_view_sha256": json_hash(schema_view),
                "confirmatory_use_allowed": False,
            }
        )
    return {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "pool_count": len(rows),
        "pools": rows,
    }


def initialize_retrievers(
    sources: dict[str, Any],
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    lexical_config = sources["lexical_config"]
    hierarchical_config = sources["hierarchical_config"]
    dense_config = sources["dense_config"]
    lexical = WeightedUnicodeNgramBM25(entries, lexical_config)
    hierarchical = ContractHierarchyTop5(entries, hierarchical_config, lexical_config)
    try:
        from Tools.core_freeze.e3_routing.dense_top5_router import FrozenDenseTop5
    except ImportError as exc:
        raise RuntimeError("dense opening generation requires the locked .venv-e3-dense runtime") from exc
    model = dense_config["embedding_model"]
    snapshot = WORKSPACE / model["cache_root"] / model["snapshot_relative_path"]
    if not snapshot.is_dir():
        raise FileNotFoundError(snapshot)
    dense = FrozenDenseTop5(entries, dense_config, snapshot)
    return {"lexical_top5": lexical, "dense_top5": dense, "hierarchical": hierarchical}


def candidate_views(
    config: dict[str, Any],
    input_tasks: dict[str, Any],
    pools: dict[str, Any],
    entry_by_id: dict[str, dict[str, Any]],
    retrievers: dict[str, Any],
) -> dict[str, Any]:
    rows = []
    view_by_key: dict[tuple[str | None, int, str], str] = {}
    for pool in pools["pools"]:
        tool_ids = pool["tool_order"]
        full_id = f"VIEW-FULL-{pool['tool_pool_size']}"
        full_tools = [entry_by_id[tool_id]["openai_tool"] for tool_id in tool_ids]
        rows.append(
            {
                "candidate_view_id": full_id,
                "task_id": None,
                "method": "full_schema",
                "tool_pool_size": pool["tool_pool_size"],
                "ordered_candidate_tool_ids": tool_ids,
                "retrieval": None,
                "openai_tools": full_tools,
                "openai_tools_sha256": json_hash(full_tools),
            }
        )
        view_by_key[(None, pool["tool_pool_size"], "full_schema")] = full_id
        for task in input_tasks["tasks"]:
            for method in EXPECTED_METHODS[1:]:
                retrieval = retrievers[method].retrieve(
                    task["problem_text"], tool_ids, top_k=config["top_k"]
                )
                selected_ids = [row["tool_id"] for row in retrieval["candidates"]]
                if len(selected_ids) != config["top_k"] or not set(selected_ids).issubset(tool_ids):
                    raise ValueError(f"invalid {method} candidates for {task['task_id']}")
                view_id = f"VIEW-{method.upper()}-{task['task_id']}-{pool['tool_pool_size']}"
                tools = [entry_by_id[tool_id]["openai_tool"] for tool_id in selected_ids]
                rows.append(
                    {
                        "candidate_view_id": view_id,
                        "task_id": task["task_id"],
                        "method": method,
                        "tool_pool_size": pool["tool_pool_size"],
                        "ordered_candidate_tool_ids": selected_ids,
                        "retrieval": retrieval,
                        "openai_tools": tools,
                        "openai_tools_sha256": json_hash(tools),
                    }
                )
                view_by_key[(task["task_id"], pool["tool_pool_size"], method)] = view_id
    if len(rows) != config["expected_candidate_view_count"]:
        raise ValueError("candidate view count does not match frozen design")
    return {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "router_visible": True,
        "gold_fields_present": False,
        "candidate_view_count": len(rows),
        "views": rows,
        "_view_by_key": view_by_key,
    }


def run_cells(
    config: dict[str, Any],
    prompt: dict[str, Any],
    input_tasks: dict[str, Any],
    pools: dict[str, Any],
    views: dict[str, Any],
) -> dict[str, Any]:
    rows = []
    view_by_key = views["_view_by_key"]
    for task in input_tasks["tasks"]:
        for pool in pools["pools"]:
            size = pool["tool_pool_size"]
            for method in config["methods"]:
                task_key = None if method == "full_schema" else task["task_id"]
                view_id = view_by_key[(task_key, size, method)]
                rows.append(
                    {
                        "cell_id": f"MT-MIX-{task['task_id']}-{size}-{method.upper()}-R1",
                        "task_id": task["task_id"],
                        "task_pair_id": task["task_pair_id"],
                        "pool_id": pool["pool_id"],
                        "pool_design": "mixed_realistic",
                        "tool_pool_size": size,
                        "method": method,
                        "candidate_view_id": view_id,
                        "selector_schema_count": size if method == "full_schema" else config["top_k"],
                        "model_run_repeat": 1,
                        "prompt_id": prompt["prompt_id"],
                        "tool_execution_allowed": False,
                        "gold_visible_to_router": False,
                        "execution_status": "not_executed",
                    }
                )
    if len(rows) != config["scheduled_cell_count"] or len({row["cell_id"] for row in rows}) != len(rows):
        raise ValueError("run-cell grid is incomplete or duplicated")
    return {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "request_payloads_materialized": False,
        "external_api_calls": 0,
        "cell_count": len(rows),
        "cells": rows,
    }


def local_gate(
    config: dict[str, Any],
    scoring: dict[str, Any],
    views: dict[str, Any],
) -> dict[str, Any]:
    scoring_by_id = {row["task_id"]: row for row in scoring["tasks"]}
    rows = []
    for view in views["views"]:
        if view["task_id"] is None:
            continue
        gold = scoring_by_id[view["task_id"]]
        visible_acceptable = set(gold["acceptable_tools_full_candidate_scope"]) & set(
            view["ordered_candidate_tool_ids"]
        )
        target_recalled = gold["source_tool_id"] in view["ordered_candidate_tool_ids"]
        rows.append(
            {
                "task_id": view["task_id"],
                "method": view["method"],
                "tool_pool_size": view["tool_pool_size"],
                "target_tool_id": gold["source_tool_id"],
                "target_recalled_at_5": target_recalled,
                "acceptable_recalled_at_5": bool(visible_acceptable),
            }
        )
    summaries = []
    for method in EXPECTED_METHODS[1:]:
        method_rows = [row for row in rows if row["method"] == method]
        summaries.append(
            {
                "method": method,
                "cell_count": len(method_rows),
                "target_recall_at_5": sum(row["target_recalled_at_5"] for row in method_rows) / len(method_rows),
                "acceptable_recall_at_5": sum(row["acceptable_recalled_at_5"] for row in method_rows) / len(method_rows),
                "local_gate_passed": all(
                    row["target_recalled_at_5"] and row["acceptable_recalled_at_5"]
                    for row in method_rows
                ),
            }
        )
    return {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "development_diagnostic_only": True,
        "summaries": summaries,
        "rows": rows,
        "all_top5_methods_passed": all(row["local_gate_passed"] for row in summaries),
        "confirmatory_inference_allowed": False,
    }


def build(
    config: dict[str, Any],
    prompt: dict[str, Any],
    *,
    retrievers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validate_design(config, prompt)
    paths = {name: validate_binding(binding) for name, binding in config["bindings"].items()}
    sources = {
        name: load_json(path)
        for name, path in paths.items()
        if path.suffix.lower() == ".json"
    }
    gold_report = sources["task_gold_report"]
    if not gold_report["development_mixed_realistic_opening_allowed"]:
        raise ValueError("task-gold candidate does not permit a development opening")
    catalog_entries = sources["schema_catalog"]["entries"]
    entry_by_id = {row["tool_id"]: row for row in catalog_entries}
    input_tasks, scoring = selected_tasks(
        config, sources["taskset"], sources["task_gold_registry"]
    )
    pools = selected_pools(config, sources["nested_pool_manifest"], entry_by_id)
    active_retrievers = retrievers or initialize_retrievers(sources, catalog_entries)
    views = candidate_views(config, input_tasks, pools, entry_by_id, active_retrievers)
    cells = run_cells(config, prompt, input_tasks, pools, views)
    gate = local_gate(config, scoring, views)
    public_views = {key: value for key, value in views.items() if not key.startswith("_")}
    public_text = canonical_json({"tasks": input_tasks, "views": public_views, "cells": cells})
    gold_absent = all(f'"{field}"' not in public_text for field in prompt["gold_fields_forbidden"])
    cf06_by_size = {row["tool_count"]: row for row in sources["cf06_runtime_report"]["size_results"]}
    cf06_passed = all(
        cf06_by_size[size]["auto_request_accepted"]
        and cf06_by_size[size]["native_function_call_returned"]
        for size in EXPECTED_POOL_SIZES
    )
    preflight = {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "opening_status": (
            "prepared_local_gate_passed_pending_external_authorization"
            if gate["all_top5_methods_passed"]
            else "prepared_blocked_local_retrieval_gate_failed"
        ),
        "design": {
            "task_count": input_tasks["task_count"],
            "pool_count": pools["pool_count"],
            "method_count": len(config["methods"]),
            "candidate_view_count": public_views["candidate_view_count"],
            "cell_count": cells["cell_count"],
        },
        "checks": {
            "all_bound_hashes_valid": True,
            "balanced_two_tasks_per_target": True,
            "mixed_pool_endpoints_complete": pools["pool_count"] == 2,
            "candidate_view_grid_complete": public_views["candidate_view_count"] == 50,
            "cell_grid_complete": cells["cell_count"] == 64,
            "gold_fields_absent_from_router_artifacts": gold_absent,
            "cf06_17_120_native_schema_feasible": cf06_passed,
            "all_top5_methods_passed_local_recall_gate": gate["all_top5_methods_passed"],
            "external_api_calls_zero": True,
            "tool_execution_zero": True,
        },
        "external_api_calls": 0,
        "tool_calls_executed": 0,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
    }
    mandatory = [value for key, value in preflight["checks"].items() if key != "all_top5_methods_passed_local_recall_gate"]
    if not all(mandatory):
        raise ValueError("offline opening preflight failed")
    return {
        "input_tasks": input_tasks,
        "scoring_registry": scoring,
        "selected_pools": pools,
        "candidate_views": public_views,
        "run_cells": cells,
        "local_gate": gate,
        "preflight": preflight,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    prompt = load_json(PROMPT_PATH)
    built = build(config, prompt)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "multitarget_mixed_config_snapshot.json": config,
        "multitarget_routing_prompt_snapshot.json": prompt,
        "multitarget_routing_input_tasks.json": built["input_tasks"],
        "multitarget_routing_scoring_registry.json": built["scoring_registry"],
        "multitarget_mixed_selected_pools.json": built["selected_pools"],
        "multitarget_candidate_views.json": built["candidate_views"],
        "multitarget_routing_run_cells.json": built["run_cells"],
        "multitarget_local_retrieval_gate.json": built["local_gate"],
        "multitarget_opening_preflight.json": built["preflight"],
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    authorization = {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "decision": "pending_user_authorization" if built["local_gate"]["all_top5_methods_passed"] else "not_eligible_local_gate_failed",
        "eligible_for_external_execution_authorization": built["local_gate"]["all_top5_methods_passed"],
        "external_data_sharing_authorized": False,
        "external_api_execution_authorized": False,
        "tool_execution_allowed": False,
        "request_payloads_materialized": False,
        "required_scope_if_authorized": "8 frozen development tasks, 17/120 mixed-realistic schemas, four methods, 64 one-shot requests, no tool execution",
        "bindings": {filename: sha256_file(output_dir / filename) for filename in sorted(artifacts)},
    }
    write_json(output_dir / "execution_authorization_request.json", authorization)
    rows = []
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name):
        if path.is_file() and path.name != "artifact_manifest.json":
            rows.append({"filename": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    write_json(
        output_dir / "artifact_manifest.json",
        {"schema_version": "1.0", "opening_id": config["opening_id"], "artifact_count": len(rows), "artifacts": rows},
    )
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
