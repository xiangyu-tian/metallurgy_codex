"""Audit cross-process reproducibility of the frozen A003 dense index."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

WORKSPACE = Path(__file__).resolve().parents[3]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from Tools.core_freeze.e3_routing.dense_top5_router import (  # noqa: E402
    FrozenDenseTop5,
    vectors_sha256,
)


DEFAULTS = {
    "schema_registry": "outputs/v11_cf05_e3_a003_controlled_pools_candidate_v1_20260809/a003_pool_schema_registry.json",
    "dense_config": "Tools/core_freeze/e3_routing/a003_dense_top5_config_v1.json",
    "tasks": "outputs/v11_cf05_e3_a002_a003_pool_views_v1_20260811/a002_a003_router_visible_tasks.json",
    "pools": "outputs/v11_cf05_e3_a002_a003_pool_views_v1_20260811/a002_a003_selected_pool_views.json",
    "frozen_vectors": "outputs/v11_cf05_e3_a003_dense_top5_candidate_v1_20260809/a003_dense_top5_vectors.npz",
}


def load_json(relative_path: str) -> Any:
    return json.loads((WORKSPACE / relative_path).read_text(encoding="utf-8"))


def vector_sha(vector: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(vector, dtype="<f4").tobytes()).hexdigest()


def worker_result() -> dict[str, Any]:
    registry = load_json(DEFAULTS["schema_registry"])
    config = load_json(DEFAULTS["dense_config"])
    tasks = load_json(DEFAULTS["tasks"])["tasks"]
    pools = load_json(DEFAULTS["pools"])["views"]
    model_path = (
        WORKSPACE
        / config["embedding_model"]["cache_root"]
        / config["embedding_model"]["snapshot_relative_path"]
    )
    retriever = FrozenDenseTop5(registry["entries"], config, model_path)
    with np.load(WORKSPACE / DEFAULTS["frozen_vectors"]) as archive:
        frozen_tool_ids = archive["tool_ids"].tolist()
        frozen_vectors = np.asarray(archive["vectors"], dtype=np.float32)
    if frozen_tool_ids != retriever.tool_ids:
        raise ValueError("frozen dense tool order differs from the current registry")

    task = next(row for row in tasks if row["task_id"] == "E3-MP-FE2O3-ELEMENTS")
    query_vector = retriever.embed_query(task["problem_text"])
    original_vectors = retriever.vectors
    rankings: dict[str, Any] = {}
    for pool in pools:
        if "120-" not in pool["view_id"]:
            continue
        rankings[pool["view_id"]] = {}
        for source, vectors in (("fresh", original_vectors), ("frozen", frozen_vectors)):
            retriever.vectors = vectors
            result = retriever.rank_vector(query_vector, pool["tool_order"], top_k=10)
            rankings[pool["view_id"]][source] = [
                {"tool_id": row["tool_id"], "score": row["score"]}
                for row in result["candidates"]
            ]
    retriever.vectors = original_vectors
    return {
        "fresh_vector_sha256": retriever.vector_sha256,
        "frozen_vector_sha256": vectors_sha256(frozen_tool_ids, frozen_vectors),
        "fresh_equals_frozen": bool(np.array_equal(original_vectors, frozen_vectors)),
        "document_sha256": retriever.document_sha256,
        "query_vector_sha256": vector_sha(query_vector),
        "rankings": rankings,
    }


def canonical_signature(result: dict[str, Any]) -> str:
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def orchestrate(process_count: int) -> dict[str, Any]:
    runs = []
    for run_index in range(1, process_count + 1):
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--worker"],
            cwd=WORKSPACE,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        result = json.loads(completed.stdout)
        runs.append(
            {
                "process_repeat": run_index,
                "result_signature_sha256": canonical_signature(result),
                "result": result,
            }
        )
    signatures = {row["result_signature_sha256"] for row in runs}
    reference = runs[0]["result"]
    frozen_rankings_equal_fresh = all(
        values["fresh"] == values["frozen"]
        for values in reference["rankings"].values()
    )
    return {
        "schema_version": "1.0",
        "audit_id": "V11-CF05-E3-A002-A003-DENSE-REPRO-AUDIT-V1-20260811",
        "process_count": process_count,
        "all_process_results_exactly_equal": len(signatures) == 1,
        "fresh_index_exactly_equals_frozen_index": reference["fresh_equals_frozen"],
        "fresh_and_frozen_rankings_exactly_equal": frozen_rankings_equal_fresh,
        "external_api_calls": 0,
        "tool_calls_executed": 0,
        "runs": runs,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--process-count", type=int, default=3)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.worker:
        print(json.dumps(worker_result(), ensure_ascii=False, sort_keys=True))
        return
    if args.process_count < 2:
        raise ValueError("process-count must be at least two")
    report = orchestrate(args.process_count)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else WORKSPACE / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
