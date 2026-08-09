"""Build and score A003 Lexical Top-5 candidate views without external calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

WORKSPACE = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "a003_lexical_top5_config_v1.json"
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from Tools.core_freeze.e3_routing.lexical_top5_router import (
    WeightedUnicodeNgramBM25,
    canonical_json,
)


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


def validate_binding(binding: dict[str, str]) -> Path:
    path = WORKSPACE / binding["path"]
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256_file(path)
    if actual != binding["sha256"].lower():
        raise ValueError(f"bound file hash mismatch for {path}: {actual}")
    return path


def validate_config(config: dict[str, Any]) -> None:
    if config["method"] != "lexical_top5":
        raise ValueError("method must remain lexical_top5")
    if config["algorithm"] != "weighted_unicode_ngram_bm25_v1":
        raise ValueError("unexpected lexical algorithm")
    if config["top_k"] != 5:
        raise ValueError("Lexical Top-5 must keep K=5")
    if config["expected_lexical_cell_count"] != 24:
        raise ValueError("expected_lexical_cell_count must remain 24")
    for field in (
        "gold_visible_to_retriever",
        "external_api_calls_authorized",
        "tool_execution_allowed",
        "confirmatory_inference_allowed",
        "independent_validation_split_access_allowed",
        "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")
    if config["query_source"] != "problem_text_only":
        raise ValueError("query_source must remain problem_text_only")
    expected_fields = {
        "tool_name",
        "semantic_alias",
        "scenario",
        "tool_type",
        "core_method",
        "main_input",
        "main_output",
        "applicable_boundary_risk",
        "function_description",
        "parameter_name",
        "parameter_description",
    }
    if set(config["field_boosts"]) != expected_fields:
        raise ValueError("field boost set changed")


def _score_views(
    views: list[dict[str, Any]], scoring_registry: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    gold_by_id = {row["task_id"]: row for row in scoring_registry["tasks"]}
    rows = []
    for view in views:
        gold = gold_by_id[view["task_id"]]
        candidate_ids = [row["tool_id"] for row in view["candidates"]]
        acceptable = set(gold["acceptable_tools"])
        acceptable_ranks = [
            index + 1
            for index, tool_id in enumerate(candidate_ids)
            if tool_id in acceptable
        ]
        target_ranks = [
            index + 1 for index, tool_id in enumerate(candidate_ids) if tool_id == "A003"
        ]
        rows.append(
            {
                "cell_id": view["cell_id"],
                "task_id": view["task_id"],
                "pool_id": view["pool_id"],
                "tool_pool_size": view["tool_pool_size"],
                "pool_repeat": view["pool_repeat"],
                "near_neighbor_type": view["near_neighbor_type"],
                "near_neighbor_count": view["near_neighbor_count"],
                "acceptable_tool_recalled_at_5": bool(acceptable_ranks),
                "best_acceptable_rank": min(acceptable_ranks) if acceptable_ranks else None,
                "acceptable_reciprocal_rank": (
                    1.0 / min(acceptable_ranks) if acceptable_ranks else 0.0
                ),
                "target_tool_recalled_at_5": bool(target_ranks),
                "target_tool_rank": min(target_ranks) if target_ranks else None,
            }
        )

    def summarize(group: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "cell_count": len(group),
            "acceptable_recall_at_5": sum(
                row["acceptable_tool_recalled_at_5"] for row in group
            )
            / len(group),
            "acceptable_mrr": sum(
                row["acceptable_reciprocal_rank"] for row in group
            )
            / len(group),
            "target_recall_at_5": sum(
                row["target_tool_recalled_at_5"] for row in group
            )
            / len(group),
            "mean_target_rank_when_recalled": (
                sum(
                    row["target_tool_rank"]
                    for row in group
                    if row["target_tool_rank"] is not None
                )
                / sum(row["target_tool_rank"] is not None for row in group)
            ),
        }

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                row["tool_pool_size"],
                row["near_neighbor_type"],
                row["near_neighbor_count"],
            )
        ].append(row)
    summary = {
        "overall": summarize(rows),
        "by_size_and_condition": [
            {
                "tool_pool_size": key[0],
                "near_neighbor_type": key[1],
                "near_neighbor_count": key[2],
                **summarize(group),
            }
            for key, group in sorted(grouped.items())
        ],
    }
    return rows, summary


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {
        name: validate_binding(binding)
        for name, binding in config["bindings"].items()
    }
    input_tasks = load_json(paths["routing_input_tasks"])
    selected_pools = load_json(paths["routing_selected_pools"])
    run_cells = load_json(paths["routing_run_cells"])
    schema_registry = load_json(paths["pool_schema_registry"])
    task_by_id = {row["task_id"]: row for row in input_tasks["tasks"]}
    pool_by_id = {row["pool_id"]: row for row in selected_pools["pools"]}
    lexical_cells = [
        row for row in run_cells["cells"] if row["method"] == "lexical_top5"
    ]
    if len(lexical_cells) != config["expected_lexical_cell_count"]:
        raise ValueError("bound opening does not contain exactly 24 lexical cells")

    retriever = WeightedUnicodeNgramBM25(schema_registry["entries"], config)
    views = []
    deterministic_rows = []
    for cell in lexical_cells:
        task = task_by_id[cell["task_id"]]
        pool = pool_by_id[cell["pool_id"]]
        started = time.perf_counter_ns()
        result = retriever.retrieve(
            task["problem_text"], pool["tool_order"], top_k=config["top_k"]
        )
        latency_ms = (time.perf_counter_ns() - started) / 1_000_000.0
        repeated = retriever.retrieve(
            task["problem_text"], pool["tool_order"], top_k=config["top_k"]
        )
        deterministic = canonical_json(result) == canonical_json(repeated)
        if not deterministic:
            raise ValueError(f"nondeterministic lexical result: {cell['cell_id']}")
        candidate_ids = [row["tool_id"] for row in result["candidates"]]
        if len(candidate_ids) != config["top_k"]:
            raise ValueError(f"wrong candidate count: {cell['cell_id']}")
        if not set(candidate_ids).issubset(pool["tool_order"]):
            raise ValueError(f"candidate escaped current pool: {cell['cell_id']}")
        views.append(
            {
                "cell_id": cell["cell_id"],
                "task_id": cell["task_id"],
                "pool_id": cell["pool_id"],
                "tool_pool_size": cell["tool_pool_size"],
                "pool_repeat": cell["pool_repeat"],
                "near_neighbor_type": cell["near_neighbor_type"],
                "near_neighbor_count": cell["near_neighbor_count"],
                "method": "lexical_top5",
                "retriever_config_sha256": sha256_file(CONFIG_PATH),
                "retrieval_latency_ms": round(latency_ms, 6),
                "candidate_tool_ids": candidate_ids,
                "candidates": result["candidates"],
                "index_sha256": result["index_sha256"],
                "query_token_count": result["query_token_count"],
                "execution_status": "candidate_view_only_no_external_api",
            }
        )
        deterministic_rows.append(
            {
                "cell_id": cell["cell_id"],
                "deterministic_repeat_equal": deterministic,
                "candidate_tool_ids": candidate_ids,
                "scores_sha256": hashlib.sha256(
                    canonical_json(
                        [row["score"] for row in result["candidates"]]
                    ).encode("utf-8")
                ).hexdigest(),
            }
        )

    serialized_views = canonical_json(views)
    forbidden = (
        "acceptable_tools",
        "revalidated_primary_acceptable_tools",
        "scoring_rule",
        "expected_parameters",
    )
    gold_fields_absent = all(f'"{field}"' not in serialized_views for field in forbidden)
    if not gold_fields_absent:
        raise ValueError("gold field leaked into lexical candidate views")

    scoring_registry = load_json(paths["routing_scoring_registry"])
    score_rows, score_summary = _score_views(views, scoring_registry)
    overall = score_summary["overall"]
    promotion_passed = (
        overall["acceptable_recall_at_5"]
        >= config["minimum_development_acceptable_recall_at_5"]
        and overall["target_recall_at_5"]
        >= config["minimum_development_target_recall_at_5"]
    )
    candidate_views = {
        "schema_version": "1.0",
        "implementation_id": config["implementation_id"],
        "method": "lexical_top5",
        "router_visible_gold": False,
        "external_api_calls": 0,
        "tool_calls_executed": 0,
        "view_count": len(views),
        "views": views,
    }
    determinism = {
        "schema_version": "1.0",
        "implementation_id": config["implementation_id"],
        "cell_count": len(deterministic_rows),
        "all_repeated_results_equal": all(
            row["deterministic_repeat_equal"] for row in deterministic_rows
        ),
        "rows": deterministic_rows,
    }
    diagnostics = {
        "schema_version": "1.0",
        "implementation_id": config["implementation_id"],
        "development_only": True,
        "confirmatory_inference_allowed": False,
        "summary": score_summary,
        "rows": score_rows,
    }
    readiness = {
        "schema_version": "1.0",
        "implementation_id": config["implementation_id"],
        "method": "lexical_top5",
        "implementation_status": (
            "candidate_implementation_passed_local_gate"
            if promotion_passed
            else "candidate_implementation_failed_local_gate"
        ),
        "ready_for_24_cell_lexical_slice_generation": promotion_passed,
        "ready_for_external_development_run": False,
        "external_execution_requires_separate_authorization": True,
        "checks": {
            "all_bound_hashes_valid": True,
            "index_document_count": retriever.document_count,
            "exact_24_lexical_views": len(views) == 24,
            "exact_top5_each_view": all(
                len(row["candidate_tool_ids"]) == 5 for row in views
            ),
            "all_candidates_within_current_pool": True,
            "all_repeated_results_equal": determinism[
                "all_repeated_results_equal"
            ],
            "gold_fields_absent_from_candidate_views": gold_fields_absent,
            "acceptable_recall_gate_passed": (
                overall["acceptable_recall_at_5"]
                >= config["minimum_development_acceptable_recall_at_5"]
            ),
            "target_recall_gate_passed": (
                overall["target_recall_at_5"]
                >= config["minimum_development_target_recall_at_5"]
            ),
            "external_api_calls_zero": True,
            "tool_execution_zero": True,
        },
        "observed_development_metrics": overall,
        "cf05_status": "in_progress",
        "core_frozen": False,
    }
    return {
        "index_snapshot": retriever.index_snapshot(),
        "candidate_views": candidate_views,
        "determinism": determinism,
        "diagnostics": diagnostics,
        "readiness": readiness,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    built = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a003_lexical_top5_config_snapshot.json": config,
        "a003_lexical_top5_index_snapshot.json": built["index_snapshot"],
        "a003_lexical_top5_candidate_views.json": built["candidate_views"],
        "a003_lexical_top5_determinism_audit.json": built["determinism"],
        "a003_lexical_top5_development_diagnostics.json": built["diagnostics"],
        "a003_lexical_top5_readiness_report.json": built["readiness"],
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    rows = []
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name):
        if path.name == "artifact_manifest.json" or not path.is_file():
            continue
        rows.append(
            {
                "filename": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    manifest = {
        "schema_version": "1.0",
        "implementation_id": config["implementation_id"],
        "artifact_count": len(rows),
        "artifacts": rows,
    }
    write_json(output_dir / "artifact_manifest.json", manifest)
    return built["readiness"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = WORKSPACE / output_dir
    print(json.dumps(build_outputs(output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
