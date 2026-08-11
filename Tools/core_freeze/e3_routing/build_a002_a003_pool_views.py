"""Freeze 17/120 A002/A003 views and revalidate pool-specific direct tools."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import sys
from pathlib import Path
from typing import Any, Callable


WORKSPACE = Path(__file__).resolve().parents[3]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common
from Tools.core_freeze.e3_routing import candidate_runtime_adapters as adapters


CONFIG_PATH = Path(__file__).with_name("a002_a003_pool_view_config_v1.json")


def nested(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def check_result(execution: dict[str, Any], task: dict[str, Any]) -> bool:
    if execution.get("success") is not True:
        return False
    for check in task["scoring_rule"]["checks"]:
        actual = nested(execution, "result." + check["path"])
        if check["op"] == "equal" and actual != check["value"]:
            return False
        if check["op"] == "approx":
            if not isinstance(actual, (int, float)) or isinstance(actual, bool):
                return False
            tolerance = float(check.get("abs_tol", 0.0)) + float(check.get("rel_tol", 0.0)) * abs(float(check["value"]))
            if not math.isfinite(float(actual)) or abs(float(actual) - float(check["value"])) > tolerance:
                return False
    return True


def invoke_candidate(tool_id: str, runtime: str, params: dict[str, Any]) -> dict[str, Any]:
    if runtime == "batch1":
        return adapters.invoke(tool_id, params)
    if runtime == "batch3":
        return adapters.invoke_batch3(tool_id, params)
    raise ValueError(f"unsupported candidate runtime: {runtime}")


def validate_config(config: dict[str, Any]) -> None:
    condition = config["selected_pool_condition"]
    if condition["tool_pool_sizes"] != [17, 120] or condition["pool_repeats"] != ["A", "B"]:
        raise ValueError("selected 17/120 A/B design changed")
    if condition["near_neighbor_type"] != "lexical" or condition["near_neighbor_count"] != 8:
        raise ValueError("A002/A003 pair-visible lexical-8 condition changed")
    if config["required_visible_endpoints"] != ["A002", "A003"]:
        raise ValueError("both family endpoints must remain visible")
    for field in ("external_api_calls_allowed", "automatic_retry_allowed", "formal_gold_mutation_allowed", "confirmatory_use_allowed", "core_frozen"):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")
    if config["local_candidate_execution_allowed"] is not True:
        raise ValueError("local candidate revalidation must remain allowed")


def validate_environment(sources: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "pymatgen": sources["candidate_environment_batch1"]["top_level_versions"]["pymatgen"],
        "periodictable": sources["candidate_environment_batch3"]["top_level_versions"]["periodictable"],
    }
    actual = {name: importlib.metadata.version(name) for name in expected}
    if actual != expected or sys.version.split()[0] != "3.11.15":
        raise RuntimeError(f"candidate environment mismatch: expected={expected}, actual={actual}, python={sys.version.split()[0]}")
    return {"python_version": sys.version.split()[0], "expected_versions": expected, "actual_versions": actual, "environment_match": True}


def build(config: dict[str, Any], invoke_fn: Callable[[str, str, dict[str, Any]], dict[str, Any]] = invoke_candidate) -> dict[str, Any]:
    validate_config(config)
    paths = {name: common.validate_binding(binding) for name, binding in config["bindings"].items()}
    sources = {name: common.load_json(path) for name, path in paths.items() if path.suffix.lower() == ".json"}
    tasks = sources["taskset"]["tasks"]
    if len(tasks) != 16:
        raise ValueError("minimal-pair task count changed")
    if sources["governance_adoption"]["decision"] != "adopted":
        raise ValueError("family governance has not been adopted")
    environment = validate_environment(sources)

    wanted = config["selected_pool_condition"]
    pools = [
        row for row in sources["pool_manifest"]["records"]
        if row["tool_pool_size"] in wanted["tool_pool_sizes"]
        and row["pool_repeat"] in wanted["pool_repeats"]
        and row["pool_design"] == wanted["pool_design"]
        and row["near_neighbor_type"] == wanted["near_neighbor_type"]
        and row["near_neighbor_count"] == wanted["near_neighbor_count"]
    ]
    if len(pools) != 4:
        raise ValueError(f"expected four selected pools, got {len(pools)}")
    schema_by_id = {row["tool_id"]: row for row in sources["schema_registry"]["entries"]}

    views = []
    signature_screen = []
    for pool in sorted(pools, key=lambda row: (row["tool_pool_size"], row["pool_repeat"])):
        order = pool["tool_order"]
        if len(order) != pool["tool_pool_size"] or len(set(order)) != len(order):
            raise ValueError(f"invalid tool order: {pool['pool_id']}")
        missing_endpoints = sorted(set(config["required_visible_endpoints"]) - set(order))
        if missing_endpoints:
            raise ValueError(f"family endpoint missing from {pool['pool_id']}: {missing_endpoints}")
        missing_schemas = [tool_id for tool_id in order if tool_id not in schema_by_id]
        if missing_schemas:
            raise ValueError(f"schema missing from {pool['pool_id']}: {missing_schemas}")
        openai_tools = [schema_by_id[tool_id]["openai_tool"] for tool_id in order]
        views.append({
            "view_id": f"A002-A003-{pool['tool_pool_size']}-{pool['pool_repeat']}-LEXICAL8-V1",
            "source_pool_id": pool["pool_id"],
            "tool_pool_size": pool["tool_pool_size"],
            "pool_repeat": pool["pool_repeat"],
            "tool_order": order,
            "family_endpoint_positions_1_based": {tool_id: order.index(tool_id) + 1 for tool_id in config["required_visible_endpoints"]},
            "openai_tools": openai_tools,
        })
        for tool_id in order:
            required = schema_by_id[tool_id]["openai_tool"]["function"]["parameters"].get("required", [])
            if required == ["formula"]:
                signature_screen.append({
                    "source_pool_id": pool["pool_id"],
                    "tool_pool_size": pool["tool_pool_size"],
                    "pool_repeat": pool["pool_repeat"],
                    "tool_id": tool_id,
                    "required_input_keys": required,
                    "direct_signature_compatible": True,
                })

    router_tasks = [{field: task[field] for field in config["router_visible_task_fields"]} for task in tasks]
    executions = []
    execution_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for task in tasks:
        for tool_id in config["direct_signature_candidate_ids"]:
            execution = invoke_fn(tool_id, config["candidate_runtime"][tool_id], dict(task["canonical_inputs"]))
            row = {
                "task_id": task["task_id"],
                "candidate_tool_id": tool_id,
                "input": task["canonical_inputs"],
                "execution": execution,
                "directly_satisfies_frozen_scoring_rule": check_result(execution, task),
            }
            executions.append(row)
            execution_by_key[(task["task_id"], tool_id)] = row

    gold_rows = []
    for task in tasks:
        for view in views:
            visible = set(view["tool_order"])
            primary = [tool_id for tool_id in config["primary_endpoint_policy"][task["pair_variant"]] if tool_id in visible]
            candidate_evidence = []
            for tool_id in config["direct_signature_candidate_ids"]:
                if tool_id not in visible:
                    continue
                evidence = execution_by_key[(task["task_id"], tool_id)]
                candidate_evidence.append({
                    "candidate_tool_id": tool_id,
                    "directly_satisfies_frozen_scoring_rule": evidence["directly_satisfies_frozen_scoring_rule"],
                })
                if evidence["directly_satisfies_frozen_scoring_rule"]:
                    primary.append(tool_id)
            gold_rows.append({
                "task_id": task["task_id"],
                "view_id": view["view_id"],
                "tool_pool_size": view["tool_pool_size"],
                "pool_repeat": view["pool_repeat"],
                "primary_acceptable_tools": sorted(set(primary)),
                "alternative_success_tools": [tool_id for tool_id in config["alternative_success_policy"][task["pair_variant"]] if tool_id in visible],
                "family_hit_tools": [tool_id for tool_id in config["required_visible_endpoints"] if tool_id in visible],
                "scientific_success_tools": sorted(set(primary) | set(tool_id for tool_id in config["alternative_success_policy"][task["pair_variant"]] if tool_id in visible)),
                "visible_direct_candidate_evidence": candidate_evidence,
                "pool_specific_acceptable_set_revalidated": True,
                "full_catalog_acceptable_set_frozen": False,
            })

    e3c002_accepts = sum(row["candidate_tool_id"] == "E3C002" and row["directly_satisfies_frozen_scoring_rule"] for row in executions)
    e3c018_accepts = sum(row["candidate_tool_id"] == "E3C018" and row["directly_satisfies_frozen_scoring_rule"] for row in executions)
    report = {
        "schema_version": "1.0",
        "package_id": config["package_id"],
        "status": "hash_frozen_pool_views_and_pool_specific_gold_candidate_built",
        "task_count": len(tasks),
        "view_count": len(views),
        "scoring_unit_count": len(gold_rows),
        "selected_pool_sizes": wanted["tool_pool_sizes"],
        "selected_pool_repeats": wanted["pool_repeats"],
        "all_views_contain_both_family_endpoints": True,
        "signature_compatible_tools_across_selected_pools": sorted({row["tool_id"] for row in signature_screen}),
        "candidate_execution_count": len(executions),
        "candidate_environment": environment,
        "e3c002_direct_acceptance_task_count": e3c002_accepts,
        "e3c018_direct_acceptance_task_count": e3c018_accepts,
        "pool_specific_acceptable_sets_revalidated": True,
        "full_catalog_acceptable_set_frozen": False,
        "external_api_calls": 0,
        "confirmatory_use_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "next_gate": "build an unauthorized development opening package from these hash-bound tasks, views, and pool-specific scoring rows",
    }
    return {"views": views, "router_tasks": router_tasks, "signature_screen": signature_screen, "executions": executions, "gold_rows": gold_rows, "report": report}


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = common.load_json(CONFIG_PATH)
    result = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a002_a003_pool_view_config_snapshot.json": config,
        "a002_a003_router_visible_tasks.json": {"schema_version": "1.0", "tasks": result["router_tasks"]},
        "a002_a003_selected_pool_views.json": {"schema_version": "1.0", "views": result["views"]},
        "a002_a003_signature_compatibility_screen.json": {"schema_version": "1.0", "rows": result["signature_screen"]},
        "a002_a003_direct_candidate_execution_results.json": {"schema_version": "1.0", "rows": result["executions"]},
        "a002_a003_pool_specific_scoring_registry.json": {"schema_version": "1.0", "rows": result["gold_rows"]},
        "a002_a003_pool_view_report.json": result["report"],
    }
    for filename, value in artifacts.items():
        common.write_json(output_dir / filename, value)
    artifact_paths = sorted(output_dir.iterdir(), key=lambda path: path.name)
    common.write_json(output_dir / "artifact_manifest.json", {
        "schema_version": "1.0",
        "package_id": config["package_id"],
        "artifact_count": len(artifact_paths),
        "artifacts": [{"filename": path.name, "sha256": common.file_hash(path), "bytes": path.stat().st_size} for path in artifact_paths],
    })
    return result["report"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else common.WORKSPACE / args.output_dir
    report = build_outputs(output_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
