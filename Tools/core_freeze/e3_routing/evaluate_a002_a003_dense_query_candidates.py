"""Evaluate predeclared dense query instructions on the frozen development set."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

WORKSPACE = Path(__file__).resolve().parents[3]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from Tools.core_freeze.e3_routing.dense_top5_router import (  # noqa: E402
    FrozenDenseTop5,
    sha256_file,
    vectors_sha256,
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def resolve_binding(binding: dict[str, str]) -> Path:
    path = WORKSPACE / binding["path"]
    if sha256_file(path) != binding["sha256"]:
        raise ValueError(f"binding hash mismatch: {binding['path']}")
    return path


def primary_rank(ranked: list[dict[str, Any]], acceptable: set[str]) -> int | None:
    return next(
        (index for index, row in enumerate(ranked, start=1) if row["tool_id"] in acceptable),
        None,
    )


def build(config_path: Path) -> dict[str, Any]:
    config = load_json(config_path)
    bindings = config["bindings"]
    tasks = load_json(resolve_binding(bindings["tasks"]))["tasks"]
    pools = load_json(resolve_binding(bindings["pool_views"]))["views"]
    scoring_rows = load_json(resolve_binding(bindings["scoring_registry"]))["rows"]
    registry = load_json(resolve_binding(bindings["schema_registry"]))
    dense_config = load_json(resolve_binding(bindings["dense_v1_config"]))
    frozen_path = resolve_binding(bindings["frozen_dense_vectors"])
    if len(tasks) != config["task_count"] or len(pools) != config["pool_view_count"]:
        raise ValueError("development grid size changed")
    for field in (
        "external_api_calls_authorized",
        "tool_execution_allowed",
        "independent_validation_split_access_allowed",
        "confirmatory_inference_allowed",
        "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")

    model_path = (
        WORKSPACE
        / dense_config["embedding_model"]["cache_root"]
        / dense_config["embedding_model"]["snapshot_relative_path"]
    )
    retriever = FrozenDenseTop5(registry["entries"], dense_config, model_path)
    with np.load(frozen_path) as archive:
        frozen_tool_ids = archive["tool_ids"].tolist()
        frozen_vectors = np.asarray(archive["vectors"], dtype=np.float32)
    if frozen_tool_ids != retriever.tool_ids:
        raise ValueError("frozen vector tool order changed")
    frozen_sha = vectors_sha256(frozen_tool_ids, frozen_vectors)
    if retriever.vector_sha256 != frozen_sha or not np.array_equal(
        retriever.vectors, frozen_vectors
    ):
        raise ValueError("fresh dense index differs from frozen dense vectors")
    retriever.vectors = frozen_vectors

    scoring = {(row["task_id"], row["view_id"]): row for row in scoring_rows}
    details = []
    summaries = []
    for candidate_order, candidate in enumerate(
        config["candidate_query_instructions"], start=1
    ):
        retriever.config["query"]["instruction_prefix"] = candidate[
            "instruction_prefix"
        ]
        query_vectors = {
            task["task_id"]: retriever.embed_query(task["problem_text"])
            for task in tasks
        }
        candidate_rows = []
        for task in tasks:
            for pool in pools:
                score = scoring[(task["task_id"], pool["view_id"])]
                full = retriever.rank_vector(
                    query_vectors[task["task_id"]],
                    pool["tool_order"],
                    top_k=len(pool["tool_order"]),
                )["candidates"]
                nearest_rank = primary_rank(
                    full, set(score["primary_acceptable_tools"])
                )
                selected = full[: config["top_k"]]
                row = {
                    "candidate_id": candidate["candidate_id"],
                    "task_id": task["task_id"],
                    "pool_view_id": pool["view_id"],
                    "tool_pool_size": len(pool["tool_order"]),
                    "selected_tool_ids": [item["tool_id"] for item in selected],
                    "nearest_primary_acceptable_rank": nearest_rank,
                    "primary_acceptable_recall_at_5": bool(
                        nearest_rank is not None and nearest_rank <= config["top_k"]
                    ),
                }
                candidate_rows.append(row)
                details.append(row)
        expected = config["expected_cell_count_per_candidate"]
        if len(candidate_rows) != expected:
            raise ValueError("candidate cell count changed")
        recall_count = sum(
            row["primary_acceptable_recall_at_5"] for row in candidate_rows
        )
        reciprocal_ranks = [
            1.0 / row["nearest_primary_acceptable_rank"] for row in candidate_rows
        ]
        summaries.append(
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_order": candidate_order,
                "role": candidate["role"],
                "instruction_prefix": candidate["instruction_prefix"],
                "cell_count": len(candidate_rows),
                "primary_acceptable_recall_at_5_count": recall_count,
                "primary_acceptable_recall_at_5_rate": recall_count / len(candidate_rows),
                "mean_reciprocal_rank_of_nearest_primary_acceptable_tool": sum(
                    reciprocal_ranks
                )
                / len(reciprocal_ranks),
                "failed_cells": [
                    {
                        "task_id": row["task_id"],
                        "pool_view_id": row["pool_view_id"],
                        "nearest_primary_acceptable_rank": row[
                            "nearest_primary_acceptable_rank"
                        ],
                    }
                    for row in candidate_rows
                    if not row["primary_acceptable_recall_at_5"]
                ],
            }
        )
    selected = sorted(
        summaries,
        key=lambda row: (
            -row["primary_acceptable_recall_at_5_count"],
            -row["mean_reciprocal_rank_of_nearest_primary_acceptable_tool"],
            row["candidate_order"],
        ),
    )[0]
    return {
        "config_snapshot": deepcopy(config),
        "details": {"schema_version": "1.0", "rows": details},
        "summary": {
            "schema_version": "1.0",
            "development_id": config["development_id"],
            "candidate_summaries": summaries,
            "selected_candidate_id": selected["candidate_id"],
            "selected_by_predeclared_rule": True,
            "selected_candidate_passes_64_of_64_recall_gate": selected[
                "primary_acceptable_recall_at_5_count"
            ]
            == config["expected_cell_count_per_candidate"],
            "fresh_index_exactly_equals_frozen_index": True,
            "frozen_vector_sha256": frozen_sha,
            "gold_visible_to_retriever": False,
            "external_api_calls": 0,
            "tool_calls_executed": 0,
            "independent_validation_split_accessed": False,
            "confirmatory_inference_allowed": False,
            "core_frozen": False,
        },
    }


def emit(output_dir: Path, built: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    files = {
        "dense_query_development_config_snapshot.json": built["config_snapshot"],
        "dense_query_candidate_results.json": built["details"],
        "dense_query_candidate_summary.json": built["summary"],
    }
    for filename, value in files.items():
        write_json(output_dir / filename, value)
    manifest_rows = []
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name):
        manifest_rows.append(
            {
                "filename": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    write_json(
        output_dir / "artifact_manifest.json",
        {"schema_version": "1.0", "artifacts": manifest_rows},
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(
            "Tools/core_freeze/e3_routing/a002_a003_dense_query_development_config_v1.json"
        ),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = args.config if args.config.is_absolute() else WORKSPACE / args.config
    output_dir = (
        args.output_dir if args.output_dir.is_absolute() else WORKSPACE / args.output_dir
    )
    built = build(config_path)
    emit(output_dir, built)
    print(json.dumps(built["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
