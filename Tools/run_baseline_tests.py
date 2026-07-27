"""运行不依赖 pytest 的 v2.0 基线与实验链路回归测试。"""

from __future__ import annotations

import os
import sys
import unittest
import json


TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, TOOLS_DIR)
sys.path.insert(0, PROJECT_DIR)

from tests import (
    test_candidate_retrieval,
    test_model_baseline,
    test_llm_experiments,
    test_thermo_fallback,
    test_tool_calling_benchmark,
    test_trace_store,
)


def main() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromModule(test_candidate_retrieval))
    suite.addTests(loader.loadTestsFromModule(test_model_baseline))
    suite.addTests(loader.loadTestsFromModule(test_llm_experiments))
    suite.addTests(loader.loadTestsFromModule(test_thermo_fallback))
    suite.addTests(loader.loadTestsFromModule(test_tool_calling_benchmark))
    suite.addTests(loader.loadTestsFromModule(test_trace_store))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    benchmark_path = os.path.join(TOOLS_DIR, "benchmarks", "golden_cases.json")
    with open(benchmark_path, encoding="utf-8") as handle:
        benchmark = json.load(handle)
    print(
        "Golden benchmark: "
        f"{benchmark['case_count']} cases, "
        f"{len(benchmark['model_coverage'])} models, "
        f"baseline {benchmark['baseline_version']}"
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
