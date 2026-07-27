"""Evaluate M4.6B candidate retrieval without calling an external LLM."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from models_core import ModelRegistry
from models_core.benchmarking import ToolCallingDataset
from models_core.candidate_retrieval import (
    CandidateModelRetriever,
    evaluate_candidate_retrieval,
)


RESULTS_DIR = Path(__file__).resolve().parent / "benchmarks" / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = ModelRegistry()
    registry.discover()
    result = evaluate_candidate_retrieval(
        ToolCallingDataset(),
        CandidateModelRetriever(registry),
        top_k=args.top_k,
    )
    result["generated_at"] = datetime.now().astimezone().isoformat()

    output_path = args.output
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = RESULTS_DIR / f"m46b_candidate_retrieval_{timestamp}.json"
    elif not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "strategy": result["strategy"],
        "dataset_version": result["dataset_version"],
        "top_k": result["top_k"],
        "summary": result["summary"],
        "output": str(output_path.resolve()),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
