"""Run a persisted DeepSeek tool-calling benchmark and save its JSON summary."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from models_core import ModelRegistry
from models_core.benchmarking import BenchmarkService, ToolCallingDataset
from models_core.llm_adapters import DeepSeekOpenAIAdapter
from models_core.llm_experiments import DeepSeekExperimentService
from models_core.services import ExperimentService, ModelExecutionService
from models_core.trace_store import create_trace_store


RESULTS_DIR = Path(__file__).resolve().parent / "benchmarks" / "results"


def _safe_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("_")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=ExperimentService.MODES,
        default=[ExperimentService.MODE_AUTONOMOUS],
    )
    parser.add_argument("--categories", nargs="+")
    parser.add_argument("--max-cases", type=int, default=120)
    parser.add_argument("--prompt-version", default="m4.6-v1")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = ModelRegistry()
    registry.discover()
    store = create_trace_store()
    store_health = store.health()
    if not store_health.get("persistent"):
        raise RuntimeError(
            "PostgreSQL trace store is unavailable; refusing an unpersisted benchmark"
        )

    executor = ModelExecutionService(registry, store)
    deterministic = ExperimentService(registry, executor, store)
    adapter = DeepSeekOpenAIAdapter.from_environment()
    deepseek = DeepSeekExperimentService(registry, executor, store, adapter)
    benchmark = BenchmarkService(
        ToolCallingDataset(),
        deterministic,
        store,
        experiment_engines={"deepseek": deepseek},
    )
    result = benchmark.run(
        engine="deepseek",
        modes=args.modes,
        categories=args.categories,
        max_cases=args.max_cases,
        prompt_version=args.prompt_version,
    )
    result["generated_at"] = datetime.now().astimezone().isoformat()
    result["trace_store"] = store_health

    output_path = args.output
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_name = _safe_filename(deepseek.default_llm_name)
        prompt_name = _safe_filename(args.prompt_version)
        output_path = RESULTS_DIR / f"{prompt_name}_{model_name}_{timestamp}.json"
    elif not output_path.is_absolute():
        output_path = Path.cwd() / output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "run_id": result["run_id"],
        "case_count": result["case_count"],
        "modes": result["modes"],
        "summary_by_mode": result["summary_by_mode"],
        "output": str(output_path.resolve()),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
