"""Build local lexical, dense and hierarchical Top-5 views for A002/A003 tasks."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common
from Tools.core_freeze.e3_routing.dense_top5_router import FrozenDenseTop5
from Tools.core_freeze.e3_routing.e3_transport_policy import load_and_validate_policy
from Tools.core_freeze.e3_routing.hierarchical_top5_router import ContractHierarchyTop5
from Tools.core_freeze.e3_routing.lexical_top5_router import WeightedUnicodeNgramBM25


CONFIG_PATH = Path(__file__).with_name("a002_a003_top5_views_config_v1.json")


def validate_design(config: dict[str, Any]) -> None:
    if config["methods"] != ["lexical_top5", "dense_top5", "hierarchical"] or config["top_k"] != 5:
        raise ValueError("Top-5 method grid changed")
    if config["task_count"] != 16 or config["pool_view_count"] != 4 or config["expected_retrieval_cell_count"] != 192:
        raise ValueError("Top-5 retrieval grid changed")
    for field in ("gold_visible_to_retriever", "external_api_calls_authorized", "tool_execution_allowed", "independent_validation_split_access_allowed", "confirmatory_inference_allowed", "core_frozen"):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")


def validate_dense_snapshot(dense_config: dict[str, Any]) -> Path:
    model = dense_config["embedding_model"]
    path = WORKSPACE / model["cache_root"] / model["snapshot_relative_path"]
    if not path.is_dir():
        raise FileNotFoundError(path)
    for filename, expected in model["expected_files"].items():
        candidate = path / filename
        if not candidate.is_file() or common.file_hash(candidate) != expected:
            raise ValueError(f"dense snapshot file mismatch: {filename}")
    return path


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_design(config)
    paths = {name: common.validate_binding(binding) for name, binding in config["bindings"].items()}
    sources = {name: common.load_json(path) for name, path in paths.items() if path.suffix.lower() == ".json"}
    dense_query_policy = sources.get("dense_query_policy")
    if dense_query_policy is not None:
        policy_paths = {
            name: common.validate_binding(binding)
            for name, binding in dense_query_policy["bindings"].items()
        }
        development_summary = common.load_json(policy_paths["development_summary"])
        if dense_query_policy["base_dense_implementation_id"] != sources["dense_config"]["implementation_id"]:
            raise ValueError("dense query policy is bound to a different base implementation")
        if development_summary["selected_candidate_id"] != dense_query_policy["selection_basis"]["predeclared_candidate_id"]:
            raise ValueError("dense query policy differs from the predeclared development selection")
        if development_summary["selected_candidate_passes_64_of_64_recall_gate"] is not True:
            raise ValueError("selected dense query candidate did not pass the development recall gate")
        for field in (
            "changes_embedding_model",
            "changes_document_renderer",
            "changes_frozen_index",
            "changes_similarity_or_tie_break",
            "external_api_calls_authorized",
            "independent_validation_split_access_allowed",
            "confirmatory_inference_allowed",
            "core_frozen",
        ):
            if dense_query_policy[field] is not False:
                raise ValueError(f"dense query policy field must remain false: {field}")
        sources["dense_config"]["query"]["instruction_prefix"] = dense_query_policy["instruction_prefix"]
    policy = load_and_validate_policy()
    if common.file_hash(paths["transport_policy"]) != common.file_hash(Path(__file__).with_name("e3_selector_transport_policy_v1.json")):
        raise ValueError("bound transport policy differs from active policy")
    tasks = sources["tasks"]["tasks"]
    pools = sources["pool_views"]["views"]
    scoring = {(row["task_id"], row["view_id"]): row for row in sources["scoring_registry"]["rows"]}
    entries = sources["schema_registry"]["entries"]
    entry_by_id = {row["tool_id"]: row for row in entries}
    if len(tasks) != 16 or len(pools) != 4:
        raise ValueError("bound task/pool grid changed")
    dense_path = validate_dense_snapshot(sources["dense_config"])
    started = time.perf_counter()
    lexical = WeightedUnicodeNgramBM25(entries, sources["lexical_config"])
    dense = FrozenDenseTop5(entries, sources["dense_config"], dense_path)
    hierarchical = ContractHierarchyTop5(entries, sources["hierarchical_config"], sources["lexical_config"])
    initialization_ms = round((time.perf_counter() - started) * 1000.0, 6)
    routers = {"lexical_top5": lexical, "dense_top5": dense, "hierarchical": hierarchical}
    results = []
    schema_views = []
    for task in tasks:
        for pool in pools:
            gold = scoring[(task["task_id"], pool["view_id"])]
            for method in config["methods"]:
                began = time.perf_counter()
                retrieval = routers[method].retrieve(task["problem_text"], pool["tool_order"], top_k=5)
                latency_ms = round((time.perf_counter() - began) * 1000.0, 6)
                selected = [row["tool_id"] for row in retrieval["candidates"]]
                if len(selected) != 5 or len(set(selected)) != 5 or not set(selected).issubset(pool["tool_order"]):
                    raise ValueError("invalid Top-5 candidate view")
                view_id = f"{task['task_id']}-{pool['view_id']}-{method.upper()}-{config.get('schema_view_version', 'V1')}"
                results.append({
                    "retrieval_id": view_id,
                    "task_id": task["task_id"],
                    "pair_id": task["pair_id"],
                    "pair_variant": task["pair_variant"],
                    "source_pool_view_id": pool["view_id"],
                    "tool_pool_size": pool["tool_pool_size"],
                    "pool_repeat": pool["pool_repeat"],
                    "method": method,
                    "query_source": "problem_text_only",
                    "selected_tool_ids": selected,
                    "primary_acceptable_recall_at_5": bool(set(selected) & set(gold["primary_acceptable_tools"])),
                    "family_recall_at_5": bool(set(selected) & set(gold["family_hit_tools"])),
                    "scientific_recall_at_5": bool(set(selected) & set(gold["scientific_success_tools"])),
                    "retrieval_latency_ms": latency_ms,
                    "retrieval": retrieval,
                    "gold_visible_to_retriever": False,
                })
                schema_views.append({
                    "schema_view_id": view_id,
                    "task_id": task["task_id"],
                    "source_pool_view_id": pool["view_id"],
                    "method": method,
                    "ordered_tool_ids": selected,
                    "tools": [entry_by_id[tool_id]["openai_tool"] for tool_id in selected],
                })
    if len(results) != 192 or len({row["retrieval_id"] for row in results}) != 192:
        raise ValueError("retrieval grid incomplete")
    method_summary = []
    for method in config["methods"]:
        rows = [row for row in results if row["method"] == method]
        method_summary.append({
            "method": method,
            "cell_count": len(rows),
            "primary_acceptable_recall_at_5_count": sum(row["primary_acceptable_recall_at_5"] for row in rows),
            "primary_acceptable_recall_at_5_rate": round(sum(row["primary_acceptable_recall_at_5"] for row in rows) / len(rows), 6),
            "family_recall_at_5_rate": round(sum(row["family_recall_at_5"] for row in rows) / len(rows), 6),
            "scientific_recall_at_5_rate": round(sum(row["scientific_recall_at_5"] for row in rows) / len(rows), 6),
        })
    all_primary = all(row["primary_acceptable_recall_at_5"] for row in results)
    report = {
        "schema_version": "1.0",
        "package_id": config["package_id"],
        "status": "top5_views_built_development_opening_eligible" if all_primary else "top5_views_built_recall_gate_failed",
        "task_count": len(tasks),
        "pool_view_count": len(pools),
        "method_count": len(config["methods"]),
        "retrieval_cell_count": len(results),
        "schema_view_count": len(schema_views),
        "router_initialization_ms": initialization_ms,
        "method_summary": method_summary,
        "all_cells_primary_acceptable_recall_at_5": all_primary,
        "transport_policy_id": policy["policy_id"],
        "gold_visible_to_retriever": False,
        "external_api_calls": 0,
        "tool_calls_executed": 0,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "next_gate": "build a hash-bound 192-request Top-5 selector opening only if all primary acceptable recall gates pass",
    }
    return {"results": results, "schema_views": schema_views, "method_summary": method_summary, "report": report, "lexical_snapshot": lexical.index_snapshot(), "dense_snapshot": dense.index_snapshot(), "hierarchical_snapshot": hierarchical.taxonomy_snapshot(), "dense_query_policy": dense_query_policy}


def build_outputs(output_dir: Path, config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = common.load_json(config_path)
    result = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a002_a003_top5_views_config_snapshot.json": config,
        "a002_a003_top5_retrieval_results.json": {"schema_version": "1.0", "rows": result["results"]},
        "a002_a003_top5_schema_views.json": {"schema_version": "1.0", "views": result["schema_views"]},
        "a002_a003_top5_method_summary.json": {"schema_version": "1.0", "rows": result["method_summary"]},
        "a002_a003_top5_views_report.json": result["report"],
        "lexical_index_snapshot.json": result["lexical_snapshot"],
        "dense_index_snapshot.json": result["dense_snapshot"],
        "hierarchical_taxonomy_snapshot.json": result["hierarchical_snapshot"],
    }
    if result["dense_query_policy"] is not None:
        artifacts["dense_query_policy_snapshot.json"] = result["dense_query_policy"]
    for filename, value in artifacts.items():
        common.write_json(output_dir / filename, value)
    paths = sorted(output_dir.iterdir(), key=lambda path: path.name)
    common.write_json(output_dir / "artifact_manifest.json", {"schema_version": "1.0", "package_id": config["package_id"], "artifact_count": len(paths), "artifacts": [{"filename": path.name, "sha256": common.file_hash(path), "bytes": path.stat().st_size} for path in paths]})
    return result["report"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    config_path = args.config if args.config.is_absolute() else WORKSPACE / args.config
    output_dir = args.output_dir if args.output_dir.is_absolute() else WORKSPACE / args.output_dir
    print(json.dumps(build_outputs(output_dir, config_path), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
