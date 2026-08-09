"""Build and score A003 Dense Top-5 candidate views without external calls."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

WORKSPACE = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "a003_dense_top5_config_v1.json"
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from Tools.core_freeze.e3_routing.dense_top5_router import (
    FrozenDenseTop5,
    canonical_json,
    sha256_file,
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def validate_binding(binding: dict[str, str]) -> Path:
    path = WORKSPACE / binding["path"]
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256_file(path)
    if actual != binding["sha256"].lower():
        raise ValueError(f"bound file hash mismatch for {path}: {actual}")
    return path


def validate_config(config: dict[str, Any]) -> None:
    if config["method"] != "dense_top5":
        raise ValueError("method must remain dense_top5")
    if config["algorithm"] != "bge_small_zh_v1_5_cosine_v1":
        raise ValueError("unexpected dense algorithm")
    if config["top_k"] != 5:
        raise ValueError("Dense Top-5 must keep K=5")
    if config["expected_dense_cell_count"] != 24:
        raise ValueError("expected_dense_cell_count must remain 24")
    if config["query"]["source"] != "problem_text_only":
        raise ValueError("query source must remain problem_text_only")
    model = config["embedding_model"]
    expected_model = {
        "public_model_id": "BAAI/bge-small-zh-v1.5",
        "fastembed_source_id": "Qdrant/bge-small-zh-v1.5",
        "snapshot_revision": "46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59",
        "dimension": 512,
        "runtime": "fastembed==0.8.0",
        "provider": "CPUExecutionProvider",
        "threads": 1,
        "local_files_only": True,
    }
    for key, expected in expected_model.items():
        if model.get(key) != expected:
            raise ValueError(f"frozen embedding model field changed: {key}")
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


def validate_runtime(lock_path: Path) -> dict[str, Any]:
    expected: dict[str, str] = {}
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, version = line.partition("==")
        if not separator:
            raise ValueError(f"invalid runtime lock line: {line}")
        expected[name] = version
    installed = {}
    mismatches = []
    for name, expected_version in expected.items():
        try:
            actual_version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual_version = None
        installed[name] = actual_version
        if actual_version != expected_version:
            mismatches.append(
                {"package": name, "expected": expected_version, "actual": actual_version}
            )
    if mismatches:
        raise ValueError(f"dense runtime lock mismatch: {mismatches}")
    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
    except Exception as exc:  # pragma: no cover - only exercised in broken envs
        raise ValueError(f"could not inspect ONNX providers: {exc}") from exc
    if "CPUExecutionProvider" not in providers:
        raise ValueError("CPUExecutionProvider is unavailable")
    return {
        "schema_version": "1.0",
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "runtime_lock_sha256": sha256_file(lock_path),
        "all_locked_versions_match": True,
        "installed_packages": installed,
        "onnx_available_providers": providers,
        "selected_provider": "CPUExecutionProvider",
    }


def validate_model_snapshot(config: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    model = config["embedding_model"]
    cache_root = (WORKSPACE / model["cache_root"]).resolve()
    snapshot = (cache_root / model["snapshot_relative_path"]).resolve()
    if cache_root not in snapshot.parents:
        raise ValueError("model snapshot escaped the configured cache root")
    if not snapshot.is_dir():
        raise FileNotFoundError(snapshot)
    rows = []
    for filename, expected_hash in sorted(model["expected_files"].items()):
        path = (snapshot / filename).resolve()
        if snapshot not in path.parents:
            raise ValueError(f"model file escaped snapshot: {filename}")
        if not path.is_file():
            raise FileNotFoundError(path)
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise ValueError(f"model file hash mismatch for {filename}: {actual_hash}")
        rows.append(
            {"filename": filename, "sha256": actual_hash, "bytes": path.stat().st_size}
        )
    return snapshot, {
        "schema_version": "1.0",
        "public_model_id": model["public_model_id"],
        "fastembed_source_id": model["fastembed_source_id"],
        "snapshot_revision": model["snapshot_revision"],
        "snapshot_path_recorded_as": model["snapshot_relative_path"],
        "all_expected_files_present_and_hash_valid": True,
        "files": rows,
    }


def _score_views(
    views: list[dict[str, Any]], scoring_registry: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    gold_by_id = {row["task_id"]: row for row in scoring_registry["tasks"]}
    rows = []
    for view in views:
        gold = gold_by_id[view["task_id"]]
        candidate_ids = view["candidate_tool_ids"]
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
        recalled = [row for row in group if row["target_tool_rank"] is not None]
        return {
            "cell_count": len(group),
            "acceptable_recall_at_5": sum(
                row["acceptable_tool_recalled_at_5"] for row in group
            )
            / len(group),
            "acceptable_mrr": sum(row["acceptable_reciprocal_rank"] for row in group)
            / len(group),
            "target_recall_at_5": sum(row["target_tool_recalled_at_5"] for row in group)
            / len(group),
            "mean_target_rank_when_recalled": (
                sum(row["target_tool_rank"] for row in recalled) / len(recalled)
                if recalled
                else None
            ),
        }

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[
            (row["tool_pool_size"], row["near_neighbor_type"], row["near_neighbor_count"])
        ].append(row)
    return rows, {
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


def _vector_hash(vector: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(vector, dtype="<f4").tobytes()).hexdigest()


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {name: validate_binding(value) for name, value in config["bindings"].items()}
    runtime_audit = validate_runtime(paths["runtime_lock"])
    snapshot_path, model_audit = validate_model_snapshot(config)
    input_tasks = load_json(paths["routing_input_tasks"])
    selected_pools = load_json(paths["routing_selected_pools"])
    run_cells = load_json(paths["routing_run_cells"])
    schema_registry = load_json(paths["pool_schema_registry"])
    task_by_id = {row["task_id"]: row for row in input_tasks["tasks"]}
    pool_by_id = {row["pool_id"]: row for row in selected_pools["pools"]}
    dense_cells = [row for row in run_cells["cells"] if row["method"] == "dense_top5"]
    if len(dense_cells) != config["expected_dense_cell_count"]:
        raise ValueError("bound opening does not contain exactly 24 dense cells")

    retriever = FrozenDenseTop5(schema_registry["entries"], config, snapshot_path)
    query_vectors: dict[str, np.ndarray] = {}
    query_audit_rows = []
    for task_id in sorted({row["task_id"] for row in dense_cells}):
        query = task_by_id[task_id]["problem_text"]
        started = time.perf_counter_ns()
        first = retriever.embed_query(query)
        first_latency_ms = (time.perf_counter_ns() - started) / 1_000_000.0
        second = retriever.embed_query(query)
        exact_equal = np.array_equal(first, second)
        if not exact_equal:
            raise ValueError(f"nondeterministic dense query embedding: {task_id}")
        query_vectors[task_id] = first
        query_audit_rows.append(
            {
                "task_id": task_id,
                "query_source": "problem_text_only",
                "instruction_prefix_applied": True,
                "embedding_latency_ms": round(first_latency_ms, 6),
                "vector_sha256": _vector_hash(first),
                "exact_repeat_equal": exact_equal,
            }
        )

    views = []
    deterministic_rows = []
    for cell in dense_cells:
        pool = pool_by_id[cell["pool_id"]]
        vector = query_vectors[cell["task_id"]]
        started = time.perf_counter_ns()
        result = retriever.rank_vector(vector, pool["tool_order"], top_k=config["top_k"])
        latency_ms = (time.perf_counter_ns() - started) / 1_000_000.0
        repeated = retriever.rank_vector(vector, pool["tool_order"], top_k=config["top_k"])
        deterministic = canonical_json(result) == canonical_json(repeated)
        if not deterministic:
            raise ValueError(f"nondeterministic dense ranking: {cell['cell_id']}")
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
                "method": "dense_top5",
                "retriever_config_sha256": sha256_file(CONFIG_PATH),
                "retrieval_latency_ms": round(latency_ms, 6),
                "candidate_tool_ids": candidate_ids,
                "candidates": result["candidates"],
                "document_sha256": result["document_sha256"],
                "vector_sha256": result["vector_sha256"],
                "query_vector_sha256": _vector_hash(vector),
                "execution_status": "candidate_view_only_local_embedding_no_external_api",
            }
        )
        deterministic_rows.append(
            {
                "cell_id": cell["cell_id"],
                "deterministic_repeat_equal": deterministic,
                "candidate_tool_ids": candidate_ids,
                "scores_sha256": hashlib.sha256(
                    canonical_json([row["score"] for row in result["candidates"]]).encode(
                        "utf-8"
                    )
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
        raise ValueError("gold field leaked into dense candidate views")
    score_rows, score_summary = _score_views(
        views, load_json(paths["routing_scoring_registry"])
    )
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
        "method": "dense_top5",
        "router_visible_gold": False,
        "external_api_calls": 0,
        "tool_calls_executed": 0,
        "view_count": len(views),
        "views": views,
    }
    determinism = {
        "schema_version": "1.0",
        "implementation_id": config["implementation_id"],
        "all_query_embedding_repeats_exactly_equal": all(
            row["exact_repeat_equal"] for row in query_audit_rows
        ),
        "all_ranking_repeats_equal": all(
            row["deterministic_repeat_equal"] for row in deterministic_rows
        ),
        "query_embeddings": query_audit_rows,
        "rankings": deterministic_rows,
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
        "method": "dense_top5",
        "implementation_status": (
            "candidate_implementation_passed_local_gate"
            if promotion_passed
            else "candidate_implementation_failed_local_gate"
        ),
        "ready_for_24_cell_dense_slice_generation": promotion_passed,
        "ready_for_external_development_run": False,
        "external_execution_requires_separate_authorization": True,
        "checks": {
            "all_bound_hashes_valid": True,
            "runtime_lock_exact": runtime_audit["all_locked_versions_match"],
            "model_snapshot_hash_valid": model_audit[
                "all_expected_files_present_and_hash_valid"
            ],
            "index_document_count": len(retriever.tool_ids),
            "embedding_dimension": int(retriever.vectors.shape[1]),
            "exact_24_dense_views": len(views) == 24,
            "exact_top5_each_view": all(len(row["candidate_tool_ids"]) == 5 for row in views),
            "all_candidates_within_current_pool": True,
            "all_query_embedding_repeats_exactly_equal": determinism[
                "all_query_embedding_repeats_exactly_equal"
            ],
            "all_ranking_repeats_equal": determinism["all_ranking_repeats_equal"],
            "gold_fields_absent_from_candidate_views": gold_fields_absent,
            "acceptable_recall_gate_passed": overall["acceptable_recall_at_5"]
            >= config["minimum_development_acceptable_recall_at_5"],
            "target_recall_gate_passed": overall["target_recall_at_5"]
            >= config["minimum_development_target_recall_at_5"],
            "external_api_calls_zero": True,
            "tool_execution_zero": True,
        },
        "observed_development_metrics": overall,
        "cf05_status": "in_progress",
        "core_frozen": False,
    }
    documents = {
        "schema_version": "1.0",
        "renderer_version": config["document_renderer"]["version"],
        "gold_fields_present": False,
        "document_count": len(retriever.tool_ids),
        "documents": [
            {"tool_id": tool_id, "text": document}
            for tool_id, document in zip(retriever.tool_ids, retriever.documents)
        ],
    }
    return {
        "runtime_audit": runtime_audit,
        "model_audit": model_audit,
        "documents": documents,
        "index_snapshot": retriever.index_snapshot(),
        "tool_ids": retriever.tool_ids,
        "vectors": retriever.vectors,
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
        "a003_dense_top5_config_snapshot.json": config,
        "a003_dense_top5_runtime_audit.json": built["runtime_audit"],
        "a003_dense_top5_model_audit.json": built["model_audit"],
        "a003_dense_top5_contract_documents.json": built["documents"],
        "a003_dense_top5_index_snapshot.json": built["index_snapshot"],
        "a003_dense_top5_candidate_views.json": built["candidate_views"],
        "a003_dense_top5_determinism_audit.json": built["determinism"],
        "a003_dense_top5_development_diagnostics.json": built["diagnostics"],
        "a003_dense_top5_readiness_report.json": built["readiness"],
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    np.savez_compressed(
        output_dir / "a003_dense_top5_vectors.npz",
        tool_ids=np.asarray(built["tool_ids"], dtype="U"),
        vectors=np.asarray(built["vectors"], dtype=np.float32),
    )
    rows = []
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name):
        if path.name == "artifact_manifest.json" or not path.is_file():
            continue
        rows.append(
            {"filename": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
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
