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
            "dataset_version": "1.2.0",
            "case_count": 120,
            "category_coverage": {
                "adversarial": 10,
                "insufficient_info": 15,
                "multi_tool": 15,
                "no_tool": 15,
                "out_of_domain": 14,
                "single_tool": 51,
            },
            "schema_version": "1.1",
            "evaluator_version": "1.1.2",
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
                self.assertTrue(case["expected_final_behavior"])
                self.assertTrue(case["acceptable_actions"])
                self.assertIn(case["answer_requirements"]["type"], {
                    "numeric", "concept_terms", "behavior", "manual",
                })

    def test_multi_tool_cases_use_scenario_specific_self_contained_inputs(self):
        calcium = self.dataset.get("TC-MULTI_TOOL-002")
        self.assertEqual(
            calcium["step_arguments"]["A002"],
            {"formula": "CaCO3"},
        )
        self.assertEqual(
            calcium["step_arguments"]["B008"],
            {"reaction": "CaCO₃ → CaO + CO₂", "temperature": 900},
        )

        phase = self.dataset.get("TC-MULTI_TOOL-006")
        for value in ("45", "35", "20", "0.4", "0.2", "0.8"):
            self.assertIn(value, phase["question"])

        kinetics = self.dataset.get("TC-MULTI_TOOL-007")
        self.assertEqual(
            kinetics["step_arguments"]["A001"],
            {"value": 800, "source_unit": "°C", "target_unit": "K"},
        )
        self.assertEqual(
            kinetics["step_arguments"]["C001"]["temperature"],
            1073.15,
        )
        for value in ("800", "1e7", "80 kJ/mol"):
            self.assertIn(value, kinetics["question"])

        balance = self.dataset.get("TC-MULTI_TOOL-010")
        self.assertIn("100 kg", balance["question"])
        self.assertEqual(
            balance["step_arguments"]["A001"],
            {"value": 100, "source_unit": "kg", "target_unit": "t"},
        )

        diffusion = self.dataset.get("TC-MULTI_TOOL-012")
        for value in ("1e-4", "60 kJ/mol", "1000 K"):
            self.assertIn(value, diffusion["question"])

        converted_balance = self.dataset.get("TC-MULTI_TOOL-014")
        self.assertEqual(
            converted_balance["expected_call_sequence"],
            ["A001", "A005"],
        )
        self.assertEqual(
            converted_balance["step_arguments"]["A001"],
            {"value": 1, "source_unit": "t", "target_unit": "kg"},
        )

    def test_every_frozen_multi_tool_step_is_executable(self):
        registry = ModelRegistry()
        registry.discover()
        for case in self.dataset.list_cases(categories=["multi_tool"]):
            for model_code in case["expected_call_sequence"]:
                with self.subTest(case=case["case_id"], model=model_code):
                    arguments = case["step_arguments"][model_code]
                    validation = registry.validate(model_code, arguments)
                    self.assertTrue(validation["valid"], validation["errors"])
                    result = registry.invoke(model_code, arguments)
                    self.assertTrue(result.success, result.error)


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
        self.assertEqual(result["summary"]["automatically_scored_experiment_count"], 9)
        self.assertEqual(result["summary"]["manual_review_experiment_count"], 0)
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
        self.assertTrue(autonomous_no_tool["metrics"]["path_compliance_correct"])
        self.assertFalse(autonomous_no_tool["metrics"]["final_answer_correct"])

        stored = self.store.get_experiment(forced_single["experiment_id"])
        self.assertEqual(stored["benchmark_case_id"], "TC-SINGLE_TOOL-001")
        self.assertEqual(stored["metrics"], forced_single["metrics"])
        self.assertEqual(stored["metrics"]["benchmark_run_id"], result["run_id"])
        self.assertEqual(stored["metrics"]["dataset_version"], "1.2.0")
        self.assertEqual(stored["metrics"]["evaluator_version"], "1.1.2")

    def test_semantic_answer_behavior_and_path_are_independent(self):
        numeric_case = self.service.dataset.get("TC-SINGLE_TOOL-001")
        expected_value = numeric_case["expected_result"]["value"]
        direct_numeric = BenchmarkService.evaluate(numeric_case, {
            "status": "completed",
            "selected_model": None,
            "tool_call_chain": [],
            "final_answer": f"计算结果为 {expected_value}。如需其他条件，请提供更多信息。",
        })
        self.assertEqual(direct_numeric["actual_final_behavior"], "direct_answer")
        self.assertTrue(direct_numeric["final_answer_correct"])
        self.assertTrue(direct_numeric["final_behavior_correct"])
        self.assertTrue(direct_numeric["semantic_case_passed"])
        self.assertFalse(direct_numeric["path_compliance_correct"])

        reject_case = self.service.dataset.get("TC-OUT_OF_DOMAIN-001")
        direct_reject = BenchmarkService.evaluate(reject_case, {
            "status": "completed",
            "selected_model": None,
            "tool_call_chain": [],
            "final_answer": "kg 与 Pa 量纲不一致，无法换算。",
        })
        self.assertEqual(direct_reject["actual_final_behavior"], "direct_reject")
        self.assertTrue(direct_reject["semantic_case_passed"])
        self.assertFalse(direct_reject["path_compliance_correct"])

    def test_concept_clarification_and_misleading_numeric_answers_are_scored(self):
        concept_case = self.service.dataset.get("TC-NO_TOOL-001")
        concept = BenchmarkService.evaluate(concept_case, {
            "status": "completed",
            "selected_model": None,
            "tool_call_chain": [],
            "final_answer": (
                "Shomate 方程是描述热容等热力学性质的经验公式。"
                "\n\n其限制是不支持相变区域。"
            ),
        })
        self.assertEqual(concept["actual_final_behavior"], "direct_answer")
        self.assertTrue(concept["final_answer_correct"])
        self.assertTrue(concept["semantic_case_passed"])

        clarify_case = self.service.dataset.get("TC-INSUFFICIENT_INFO-001")
        clarification = BenchmarkService.evaluate(clarify_case, {
            "status": "completed",
            "selected_model": None,
            "tool_call_chain": [],
            "final_answer": "我需要先明确具体反应式。\n\n请提供反应温度。",
        })
        self.assertEqual(clarification["actual_final_behavior"], "clarify")
        self.assertTrue(clarification["semantic_case_passed"])

        reject_case = self.service.dataset.get("TC-OUT_OF_DOMAIN-001")
        rejection = BenchmarkService.evaluate(reject_case, {
            "status": "completed",
            "selected_model": None,
            "tool_call_chain": [],
            "final_answer": (
                "我无法执行这个换算，kg 与 Pa 属于不同的物理量纲，不能直接换算。"
                "\n\n请补充更多信息。"
            ),
        })
        self.assertEqual(rejection["actual_final_behavior"], "direct_reject")
        self.assertTrue(rejection["semantic_case_passed"])

        adversarial_case = self.service.dataset.get("TC-ADVERSARIAL-001")
        wrong_answer = BenchmarkService.evaluate(adversarial_case, {
            "status": "completed",
            "selected_model": None,
            "tool_call_chain": [],
            "final_answer": "Fe2O3 的摩尔质量是 100 g/mol。",
        })
        self.assertFalse(wrong_answer["final_answer_correct"])
        self.assertFalse(wrong_answer["semantic_case_passed"])

    def test_manual_multi_tool_answers_do_not_pollute_semantic_accuracy(self):
        case = self.service.dataset.get("TC-MULTI_TOOL-004")
        chain = [
            {
                "model_code": model_code,
                "generated_arguments": case["step_arguments"][model_code],
                "validation_result": {"valid": True, "errors": []},
                "execution_result": {"status": "success", "output": {}},
            }
            for model_code in case["expected_call_sequence"]
        ]
        metrics = BenchmarkService.evaluate(case, {
            "status": "completed",
            "selected_model": case["expected_call_sequence"][0],
            "generated_arguments": case["standard_arguments"],
            "validation_result": {"valid": True, "errors": []},
            "execution_result": {"status": "success", "output": {}},
            "tool_call_chain": chain,
            "final_answer": "组合计算完成。",
        })
        self.assertTrue(metrics["path_compliance_correct"])
        self.assertIsNone(metrics["final_answer_correct"])
        self.assertIsNone(metrics["semantic_case_passed"])
        self.assertIsNone(metrics["strict_case_passed"])
        self.assertEqual(metrics["case_passed_basis"], "manual_required")

    def test_numeric_answers_accept_scientific_percentage_and_fraction_forms(self):
        diffusion_case = self.service.dataset.get("TC-SINGLE_TOOL-049")
        scientific = BenchmarkService.evaluate(diffusion_case, {
            "status": "completed",
            "selected_model": None,
            "tool_call_chain": [],
            "final_answer": "扩散系数 D = 2.44441 \\times 10^{-7} m²/s。",
        })
        self.assertTrue(scientific["final_answer_correct"])

        phase_case = self.service.dataset.get("TC-SINGLE_TOOL-043")
        percentage = BenchmarkService.evaluate(phase_case, {
            "status": "completed",
            "selected_model": None,
            "tool_call_chain": [],
            "final_answer": "第二相分数为 25%。",
        })
        fraction = BenchmarkService.evaluate(phase_case, {
            "status": "completed",
            "selected_model": None,
            "tool_call_chain": [],
            "final_answer": "第二相约占 1/4。",
        })
        self.assertTrue(percentage["final_answer_correct"])
        self.assertTrue(fraction["final_answer_correct"])

    def test_rejections_are_effective_and_unneeded_successes_are_ineffective(self):
        reject_case = self.service.dataset.get("TC-OUT_OF_DOMAIN-001")
        rejected = BenchmarkService.evaluate(reject_case, {
            "status": "completed",
            "selected_model": "A001",
            "generated_arguments": reject_case["standard_arguments"],
            "validation_result": {"valid": False, "errors": []},
            "execution_result": None,
            "tool_call_chain": [{
                "model_code": "A001",
                "generated_arguments": reject_case["standard_arguments"],
                "validation_result": {"valid": False, "errors": []},
                "execution_result": None,
            }],
            "final_answer": "kg 与 Pa 量纲不一致，不能换算。",
        })
        self.assertEqual(rejected["unsuccessful_call_count"], 1)
        self.assertEqual(rejected["unnecessary_call_count"], 0)
        self.assertEqual(rejected["ineffective_call_count"], 0)

        concept_case = self.service.dataset.get("TC-NO_TOOL-001")
        unnecessary = BenchmarkService.evaluate(concept_case, {
            "status": "completed",
            "selected_model": "A003",
            "generated_arguments": {"formula": "Fe2O3"},
            "validation_result": {"valid": True, "errors": []},
            "execution_result": {"status": "success", "output": {}},
            "tool_call_chain": [{
                "model_code": "A003",
                "generated_arguments": {"formula": "Fe2O3"},
                "validation_result": {"valid": True, "errors": []},
                "execution_result": {"status": "success", "output": {}},
            }],
            "final_answer": "Shomate 方程是描述热容的经验公式。",
        })
        self.assertEqual(unnecessary["unsuccessful_call_count"], 0)
        self.assertEqual(unnecessary["unnecessary_call_count"], 1)
        self.assertEqual(unnecessary["ineffective_call_count"], 1)

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
