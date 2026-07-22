"""Regression tests for the six-category tool-calling benchmark."""

import os
import sys
import unittest
import json
from decimal import Decimal
from types import SimpleNamespace


TOOLS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, TOOLS_DIR)

from models_core import ModelRegistry
from models_core.base import ModelResult
from models_core.benchmarking import (
    REQUIRED_CATEGORIES,
    BenchmarkService,
    ToolCallingDataset,
)
from models_core.services import ExperimentService, ModelExecutionService
from models_core.trace_store import InMemoryTraceStore


class ToolCallingDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = ToolCallingDataset()

    def test_materialized_dataset_has_fixed_six_category_coverage(self):
        self.assertEqual(self.dataset.summary(), {
            "dataset_name": "Metallurgy Tool Calling Benchmark",
            "dataset_version": "1.0.0",
            "case_count": 120,
            "category_coverage": {
                "adversarial": 10,
                "insufficient_info": 15,
                "multi_tool": 15,
                "no_tool": 15,
                "out_of_domain": 14,
                "single_tool": 51,
            },
            "schema_version": "1.0",
        })
        self.assertEqual(
            {case["category"] for case in self.dataset.list_cases()},
            REQUIRED_CATEGORIES,
        )

    def test_every_case_satisfies_the_reusable_contract(self):
        for case in self.dataset.list_cases():
            with self.subTest(case=case["case_id"]):
                self.assertFalse(ToolCallingDataset.REQUIRED_FIELDS - case.keys())
                self.assertTrue(case["question"].strip())
                self.assertIsInstance(case["standard_arguments"], dict)
                self.assertIsInstance(case["expected_call_sequence"], list)
                self.assertTrue(case["standard_answer"].strip())


class BenchmarkServiceTests(unittest.TestCase):
    def setUp(self):
        registry = ModelRegistry()
        registry.discover()
        self.store = InMemoryTraceStore()
        experiments = ExperimentService(
            registry,
            ModelExecutionService(registry, self.store),
            self.store,
        )
        self.service = BenchmarkService(
            ToolCallingDataset(),
            experiments,
            self.store,
        )

    def test_selected_cases_run_across_all_three_modes_and_save_metrics(self):
        result = self.service.run(
            case_ids=[
                "TC-NO_TOOL-001",
                "TC-SINGLE_TOOL-001",
                "TC-OUT_OF_DOMAIN-001",
            ],
            max_cases=3,
        )

        self.assertEqual(result["case_count"], 3)
        self.assertEqual(result["total_experiments"], 9)
        self.assertEqual(
            set(result["summary_by_mode"]),
            {"direct", "forced", "autonomous"},
        )

        forced_single = next(
            row for row in result["results"]
            if row["case_id"] == "TC-SINGLE_TOOL-001" and row["mode"] == "forced"
        )
        self.assertEqual(forced_single["selected_model"], "A001")
        self.assertTrue(forced_single["metrics"]["numeric_result_correct"])
        self.assertTrue(forced_single["metrics"]["case_passed"])

        autonomous_no_tool = next(
            row for row in result["results"]
            if row["case_id"] == "TC-NO_TOOL-001" and row["mode"] == "autonomous"
        )
        self.assertFalse(autonomous_no_tool["metrics"]["actual_called"])
        self.assertTrue(autonomous_no_tool["metrics"]["case_passed"])

        stored = self.store.get_experiment(forced_single["experiment_id"])
        self.assertEqual(stored["benchmark_case_id"], "TC-SINGLE_TOOL-001")
        self.assertEqual(stored["metrics"], forced_single["metrics"])
        self.assertEqual(stored["metrics"]["benchmark_run_id"], result["run_id"])
        self.assertEqual(stored["metrics"]["dataset_version"], "1.0.0")

    def test_invalid_mode_is_rejected_before_execution(self):
        with self.assertRaises(ValueError):
            self.service.run(
                modes=["unknown"],
                case_ids=["TC-NO_TOOL-001"],
                max_cases=1,
            )

    def test_execution_protocol_normalizes_database_decimals_to_json_numbers(self):
        registry = SimpleNamespace(
            get=lambda _model_code: SimpleNamespace(version="1.0.0"),
            invoke=lambda _model_code, _arguments, context: ModelResult(
                success=True,
                result={"temperature_range": [Decimal("298.0000"), Decimal("1812.0000")]},
                trace_id=context.trace_id,
            ),
        )
        executor = ModelExecutionService(registry, self.store)

        record = executor.execute("B001", {})

        self.assertEqual(record["output"]["temperature_range"], [298.0, 1812.0])
        self.assertIsInstance(record["output"]["temperature_range"][0], float)
        json.dumps(record)


if __name__ == "__main__":
    unittest.main()
