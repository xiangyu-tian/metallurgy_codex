"""Build the offline A004 hard-case 0/4 controlled-neighbor opening package."""

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
CONFIG_PATH = HERE / "a004_hardcase_opening_config_v1.json"
EXPECTED_METHODS = ["full_schema", "lexical_top5", "dense_top5", "hierarchical"]
EXPECTED_SIZES = [17, 120]
EXPECTED_CONDITIONS = ["none_0", "lexical_4", "contract_mismatch_4"]


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
    if config["target_tool_id"] != "A004":
        raise ValueError("target_tool_id must remain A004")
    if config["selected_pool_sizes"] != EXPECTED_SIZES:
        raise ValueError("selected_pool_sizes must remain [17, 120]")
    if config["methods"] != EXPECTED_METHODS or config["top_k"] != 5:
        raise ValueError("methods must remain the four non-Oracle methods with Top-5")
    if config["model_run_repeats"] != [1]:
        raise ValueError("opening must remain a one-repeat development slice")
    if config["scheduled_cell_count"] != 48 or config["expected_candidate_view_count"] != 42:
        raise ValueError("opening must remain the frozen 48-cell/42-view slice")
    conditions = config["neighbor_conditions"]
    if [row["condition_id"] for row in conditions] != EXPECTED_CONDITIONS:
        raise ValueError("neighbor condition order changed")
    expected_doses = [("none", 0), ("lexical", 4), ("contract_mismatch", 4)]
    if [(row["near_neighbor_type"], row["near_neighbor_count"]) for row in conditions] != expected_doses:
        raise ValueError("neighbor doses must remain none-0/lexical-4/contract-mismatch-4")
    if len(config["selected_task_ids"]) != 2:
        raise ValueError("opening must contain exactly two A004 hard cases")
    for field in (
        "tool_execution_allowed", "external_api_calls_authorized",
        "confirmatory_inference_allowed", "formal_pool_use_allowed",
        "gold_visible_to_router", "independent_validation_split_access_allowed",
        "full_registry_gold_claim_allowed", "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")
    if prompt["selector_policy"]["tool_execution_allowed"] is not False:
        raise ValueError("prompt must prohibit tool execution")


def normalize_candidate(row: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(row)
    normalized["tool_id"] = row.get("tool_id") or row["candidate_tool_id"]
    normalized.setdefault("tool_type", "确定性公式/规则")
    normalized.setdefault("applicable_boundary_risk", row["openai_tool"]["function"]["description"])
    return normalized


def load_entry_registry(sources: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    base = deepcopy(sources["schema_catalog"]["entries"])
    extras: list[dict[str, Any]] = []
    for name in ("batch1_registry", "batch2_registry", "batch4_registry"):
        extras.extend(normalize_candidate(row) for row in sources[name]["candidates"])
    entries = base + extras
    entry_by_id = {row["tool_id"]: row for row in entries}
    if len(entry_by_id) != len(entries):
        raise ValueError("duplicate tool id across base and candidate registries")
    return entries, entry_by_id


def select_tasks(config: dict[str, Any], taskset: dict[str, Any], gold: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    task_by_id = {row["task_id"]: row for row in taskset["tasks"]}
    gold_by_id = {row["task_id"]: row for row in gold["tasks"]}
    public_rows, scoring_rows = [], []
    for task_id in config["selected_task_ids"]:
        task, score = task_by_id[task_id], gold_by_id[task_id]
        if task["source_tool_id"] != "A004" or score["revalidated_primary_acceptable_tools"] != ["A004"]:
            raise ValueError(f"{task_id} is not an A004-only hard case")
        public_rows.append({
            "task_id": task_id,
            "task_family_id": task["task_family_id"],
            "task_pair_id": task["task_pair_id"],
            "base_task_group_id": task["base_task_group_id"],
            "precision_policy": task["precision_policy"],
            "problem_text": task["problem_text"],
        })
        scoring_rows.append({
            "task_id": task_id,
            "target_tool_id": "A004",
            "canonical_inputs": deepcopy(task["canonical_inputs"]),
            "expected_parameters": deepcopy(task["expected_parameters"]),
            "scoring_rule": deepcopy(score["scoring_rule"]),
            "acceptable_tools_development_scope": ["A004"],
        })
    return (
        {"schema_version": "1.0", "opening_id": config["opening_id"], "router_visible": True,
         "gold_fields_present": False, "task_count": len(public_rows), "tasks": public_rows},
        {"schema_version": "1.0", "opening_id": config["opening_id"], "router_visible": False,
         "use": "offline_scoring_only", "task_count": len(scoring_rows), "tasks": scoring_rows},
    )


def validate_relation_evidence(config: dict[str, Any], sources: dict[str, Any]) -> dict[str, Any]:
    combined = sources["combined_relation_registry"]["relations"]
    relation_by_pair = {(row["target_tool_id"], row["candidate_tool_id"]): row for row in combined}
    base_target = next(row for row in sources["base_neighbor_matrix"]["targets"] if row["target_tool_id"] == "A004")
    base_lexical = {row["candidate_tool_id"] for row in base_target["lexical_candidates"] if row["algorithmic_lexical_candidate"]}
    rows = []
    for condition in config["neighbor_conditions"][1:]:
        for tool_id in condition["tool_ids"]:
            if tool_id == "A003":
                passed = tool_id in base_lexical and condition["near_neighbor_type"] == "lexical"
                source = "bound_base_neighbor_matrix"
            else:
                evidence = relation_by_pair.get(("A004", tool_id), {})
                passed = evidence.get("relation_registry_admitted") is True and evidence.get("relation_type") == condition["near_neighbor_type"]
                source = "bound_combined_relation_registry"
            rows.append({"target_tool_id": "A004", "neighbor_tool_id": tool_id,
                         "relation_type": condition["near_neighbor_type"], "evidence_source": source,
                         "relation_evidence_passed": passed})
    if len(rows) != 8 or not all(row["relation_evidence_passed"] for row in rows):
        raise ValueError("A004 4+4 relation evidence is incomplete")
    return {"schema_version": "1.0", "opening_id": config["opening_id"], "relation_count": 8,
            "lexical_count": 4, "contract_mismatch_count": 4, "relations": rows,
            "confirmatory_use_allowed": False}


def build_pools(config: dict[str, Any], base_entries: list[dict[str, Any]], entry_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    relation_ids = {tool_id for row in config["neighbor_conditions"] for tool_id in row["tool_ids"]}
    neutral_base = [row["tool_id"] for row in base_entries if row["tool_id"] not in relation_ids | {"A004"}]
    if len(neutral_base) != 118:
        raise ValueError(f"expected 118 neutral base tools, got {len(neutral_base)}")
    common_120, common_17 = neutral_base[:115], neutral_base[:12]
    none_fillers = neutral_base[115:118] + config["neutral_filler_tool_ids"]
    if len(none_fillers) != 4:
        raise ValueError("none-0 requires four neutral replacements")
    rows = []
    for condition in config["neighbor_conditions"]:
        additions = none_fillers if condition["near_neighbor_count"] == 0 else condition["tool_ids"]
        for size, common in ((17, common_17), (120, common_120)):
            tool_ids = ["A004"] + common + additions
            if len(tool_ids) != size or len(set(tool_ids)) != size:
                raise ValueError(f"invalid {condition['condition_id']} pool size {size}")
            missing = [tool_id for tool_id in tool_ids if tool_id not in entry_by_id]
            if missing:
                raise ValueError(f"schemas missing for {missing}")
            rows.append({
                "pool_id": f"A004-{condition['condition_id'].upper()}-{size}",
                "pool_design": "controlled_dose_development",
                "condition_id": condition["condition_id"],
                "near_neighbor_type": condition["near_neighbor_type"],
                "near_neighbor_count": condition["near_neighbor_count"],
                "tool_pool_size": size,
                "tool_order": tool_ids,
                "tool_order_sha256": json_hash(tool_ids),
                "full_schema_view_sha256": json_hash([entry_by_id[x]["openai_tool"] for x in tool_ids]),
                "formal_pool_use_allowed": False,
            })
    by_key = {(row["condition_id"], row["tool_pool_size"]): row for row in rows}
    for condition_id in EXPECTED_CONDITIONS:
        if not set(by_key[(condition_id, 17)]["tool_order"]).issubset(by_key[(condition_id, 120)]["tool_order"]):
            raise ValueError(f"17 pool is not nested in 120 for {condition_id}")
    all_neighbors = set().union(*(set(row["tool_ids"]) for row in config["neighbor_conditions"][1:]))
    none_ids = set(by_key[("none_0", 120)]["tool_order"])
    if none_ids & all_neighbors:
        raise ValueError("none-0 pool contains a frozen A004 near neighbor")
    for condition in config["neighbor_conditions"][1:]:
        own, other = set(condition["tool_ids"]), all_neighbors - set(condition["tool_ids"])
        pool_ids = set(by_key[(condition["condition_id"], 120)]["tool_order"])
        if not own.issubset(pool_ids) or pool_ids & other:
            raise ValueError(f"relation dose contamination in {condition['condition_id']}")
    return {"schema_version": "1.0", "opening_id": config["opening_id"], "pool_count": 6,
            "common_neutral_base_count_17": 12, "common_neutral_base_count_120": 115,
            "pools": rows, "confirmatory_use_allowed": False}


def initialize_retrievers(sources: dict[str, Any], entries: list[dict[str, Any]]) -> dict[str, Any]:
    lexical = WeightedUnicodeNgramBM25(entries, sources["lexical_config"])
    hierarchical = ContractHierarchyTop5(entries, sources["hierarchical_config"], sources["lexical_config"])
    try:
        from Tools.core_freeze.e3_routing.dense_top5_router import FrozenDenseTop5
    except ImportError as exc:
        raise RuntimeError("dense opening generation requires the locked .venv-e3-dense runtime") from exc
    model = sources["dense_config"]["embedding_model"]
    snapshot = WORKSPACE / model["cache_root"] / model["snapshot_relative_path"]
    dense = FrozenDenseTop5(entries, sources["dense_config"], snapshot)
    return {"lexical_top5": lexical, "dense_top5": dense, "hierarchical": hierarchical}


def build_views(config: dict[str, Any], tasks: dict[str, Any], pools: dict[str, Any], entry_by_id: dict[str, dict[str, Any]], retrievers: dict[str, Any]) -> dict[str, Any]:
    rows, lookup = [], {}
    for pool in pools["pools"]:
        key_prefix = (pool["condition_id"], pool["tool_pool_size"])
        full_id = f"VIEW-A004-{pool['condition_id'].upper()}-{pool['tool_pool_size']}-FULL"
        full_tools = [entry_by_id[x]["openai_tool"] for x in pool["tool_order"]]
        rows.append({"candidate_view_id": full_id, "task_id": None, "method": "full_schema",
                     "condition_id": pool["condition_id"], "tool_pool_size": pool["tool_pool_size"],
                     "ordered_candidate_tool_ids": pool["tool_order"], "retrieval": None,
                     "openai_tools": full_tools, "openai_tools_sha256": json_hash(full_tools)})
        lookup[(None, *key_prefix, "full_schema")] = full_id
        for task in tasks["tasks"]:
            for method in EXPECTED_METHODS[1:]:
                retrieval = retrievers[method].retrieve(task["problem_text"], pool["tool_order"], top_k=5)
                selected = [row["tool_id"] for row in retrieval["candidates"]]
                if len(selected) != 5 or not set(selected).issubset(pool["tool_order"]):
                    raise ValueError(f"invalid {method} view for {task['task_id']}")
                view_id = f"VIEW-A004-{pool['condition_id'].upper()}-{task['task_id']}-{pool['tool_pool_size']}-{method.upper()}"
                tools = [entry_by_id[x]["openai_tool"] for x in selected]
                rows.append({"candidate_view_id": view_id, "task_id": task["task_id"], "method": method,
                             "condition_id": pool["condition_id"], "tool_pool_size": pool["tool_pool_size"],
                             "ordered_candidate_tool_ids": selected, "retrieval": retrieval,
                             "openai_tools": tools, "openai_tools_sha256": json_hash(tools)})
                lookup[(task["task_id"], *key_prefix, method)] = view_id
    if len(rows) != 42:
        raise ValueError("candidate view grid is incomplete")
    return {"schema_version": "1.0", "opening_id": config["opening_id"], "router_visible": True,
            "gold_fields_present": False, "candidate_view_count": len(rows), "views": rows,
            "_lookup": lookup}


def build_cells(config: dict[str, Any], prompt: dict[str, Any], tasks: dict[str, Any], pools: dict[str, Any], views: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for task in tasks["tasks"]:
        for pool in pools["pools"]:
            for method in EXPECTED_METHODS:
                view_id = views["_lookup"][(None if method == "full_schema" else task["task_id"], pool["condition_id"], pool["tool_pool_size"], method)]
                rows.append({"cell_id": f"A004-HARD-{task['task_id']}-{pool['condition_id'].upper()}-{pool['tool_pool_size']}-{method.upper()}-R1",
                             "task_id": task["task_id"], "task_pair_id": task["task_pair_id"],
                             "pool_id": pool["pool_id"], "pool_design": "controlled_dose_development",
                             "condition_id": pool["condition_id"], "near_neighbor_type": pool["near_neighbor_type"],
                             "near_neighbor_count": pool["near_neighbor_count"], "tool_pool_size": pool["tool_pool_size"],
                             "method": method, "candidate_view_id": view_id,
                             "selector_schema_count": pool["tool_pool_size"] if method == "full_schema" else 5,
                             "model_run_repeat": 1, "prompt_id": prompt["prompt_id"],
                             "tool_execution_allowed": False, "gold_visible_to_router": False,
                             "execution_status": "not_executed"})
    if len(rows) != 48 or len({row["cell_id"] for row in rows}) != 48:
        raise ValueError("run cell grid is incomplete")
    return {"schema_version": "1.0", "opening_id": config["opening_id"],
            "request_payloads_materialized": False, "external_api_calls": 0,
            "cell_count": len(rows), "cells": rows}


def retrieval_gate(config: dict[str, Any], views: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for view in views["views"]:
        if view["task_id"] is None:
            continue
        recalled = "A004" in view["ordered_candidate_tool_ids"]
        rows.append({"task_id": view["task_id"], "condition_id": view["condition_id"],
                     "tool_pool_size": view["tool_pool_size"], "method": view["method"],
                     "target_tool_id": "A004", "target_recalled_at_5": recalled})
    summaries = []
    for method in EXPECTED_METHODS[1:]:
        subset = [row for row in rows if row["method"] == method]
        summaries.append({"method": method, "cell_count": len(subset),
                          "target_recall_at_5": sum(row["target_recalled_at_5"] for row in subset) / len(subset),
                          "local_gate_passed": all(row["target_recalled_at_5"] for row in subset)})
    return {"schema_version": "1.0", "opening_id": config["opening_id"],
            "development_diagnostic_only": True, "summaries": summaries, "rows": rows,
            "all_top5_methods_passed": all(row["local_gate_passed"] for row in summaries),
            "confirmatory_inference_allowed": False}


def build(config: dict[str, Any], *, retrievers: dict[str, Any] | None = None) -> dict[str, Any]:
    paths = {name: validate_binding(binding) for name, binding in config["bindings"].items()}
    sources = {name: load_json(path) for name, path in paths.items() if path.suffix.lower() == ".json"}
    prompt = sources["prompt"]
    validate_design(config, prompt)
    entries, entry_by_id = load_entry_registry(sources)
    tasks, scoring = select_tasks(config, sources["taskset"], sources["task_gold_registry"])
    relations = validate_relation_evidence(config, sources)
    pools = build_pools(config, sources["schema_catalog"]["entries"], entry_by_id)
    used_ids = sorted({x for pool in pools["pools"] for x in pool["tool_order"]})
    schema_registry = {"schema_version": "1.0", "opening_id": config["opening_id"],
                       "entry_count": len(used_ids), "entries": [entry_by_id[x] for x in used_ids],
                       "formal_catalog_mutated": False}
    active = retrievers or initialize_retrievers(sources, entries)
    views = build_views(config, tasks, pools, entry_by_id, active)
    cells = build_cells(config, prompt, tasks, pools, views)
    gate = retrieval_gate(config, views)
    public_views = {key: value for key, value in views.items() if not key.startswith("_")}
    public_text = canonical_json({"tasks": tasks, "pools": pools, "views": public_views, "cells": cells})
    gold_absent = all(f'"{field}"' not in public_text for field in prompt["gold_fields_forbidden"])
    checks = {
        "all_bound_hashes_valid": True, "two_a004_only_hard_cases": tasks["task_count"] == 2,
        "relation_evidence_4_plus_4_complete": relations["relation_count"] == 8,
        "controlled_pool_grid_complete": pools["pool_count"] == 6,
        "nested_17_in_120_each_condition": True, "condition_doses_uncontaminated": True,
        "candidate_view_grid_complete": public_views["candidate_view_count"] == 42,
        "run_cell_grid_complete": cells["cell_count"] == 48,
        "gold_fields_absent_from_router_artifacts": gold_absent,
        "all_top5_methods_passed_local_recall_gate": gate["all_top5_methods_passed"],
        "external_api_calls_zero": True, "tool_execution_zero": True,
        "formal_catalog_unchanged_at_120": sources["schema_catalog"]["entry_count"] == 120,
    }
    preflight = {"schema_version": "1.0", "opening_id": config["opening_id"],
                 "opening_status": "prepared_local_gate_passed_pending_external_authorization" if gate["all_top5_methods_passed"] else "prepared_blocked_local_retrieval_gate_failed",
                 "design": {"task_count": 2, "condition_count": 3, "pool_count": 6,
                            "method_count": 4, "candidate_view_count": 42, "cell_count": 48},
                 "checks": checks, "external_api_calls": 0, "tool_calls_executed": 0,
                 "confirmatory_inference_allowed": False, "formal_pool_use_allowed": False,
                 "cf05_status": "in_progress", "core_frozen": False}
    mandatory = [value for key, value in checks.items() if key != "all_top5_methods_passed_local_recall_gate"]
    if not all(mandatory):
        raise ValueError("offline opening preflight failed")
    return {"prompt": prompt, "input_tasks": tasks, "scoring_registry": scoring,
            "relation_evidence": relations, "selected_pools": pools, "schema_registry": schema_registry,
            "candidate_views": public_views, "run_cells": cells, "local_gate": gate, "preflight": preflight}


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    built = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a004_hardcase_config_snapshot.json": config,
        "a004_hardcase_prompt_snapshot.json": built["prompt"],
        "a004_hardcase_input_tasks.json": built["input_tasks"],
        "a004_hardcase_scoring_registry.json": built["scoring_registry"],
        "a004_relation_evidence_snapshot.json": built["relation_evidence"],
        "a004_controlled_selected_pools.json": built["selected_pools"],
        "a004_pool_schema_registry.json": built["schema_registry"],
        "a004_candidate_views.json": built["candidate_views"],
        "a004_routing_run_cells.json": built["run_cells"],
        "a004_local_retrieval_gate.json": built["local_gate"],
        "a004_opening_preflight.json": built["preflight"],
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    authorization = {
        "schema_version": "1.0", "opening_id": config["opening_id"],
        "decision": "pending_user_authorization" if built["local_gate"]["all_top5_methods_passed"] else "not_eligible_local_gate_failed",
        "eligible_for_external_execution_authorization": built["local_gate"]["all_top5_methods_passed"],
        "external_data_sharing_authorized": False, "external_api_execution_authorized": False,
        "tool_execution_allowed": False, "request_payloads_materialized": False,
        "required_scope_if_authorized": "2 frozen A004 hard cases, none-0/lexical-4/contract-mismatch-4 controlled pools at 17/120, four methods, 48 one-shot requests, no tool execution",
        "bindings": {name: sha256_file(output_dir / name) for name in sorted(artifacts)},
    }
    write_json(output_dir / "execution_authorization_request.json", authorization)
    rows = []
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name):
        if path.is_file() and path.name != "artifact_manifest.json":
            rows.append({"filename": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    write_json(output_dir / "artifact_manifest.json",
               {"schema_version": "1.0", "opening_id": config["opening_id"],
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
