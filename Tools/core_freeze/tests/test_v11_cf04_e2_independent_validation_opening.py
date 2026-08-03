import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Tools.core_freeze.e2_contract_boundaries import (
    build_e2_independent_validation_opening as opening,
    run_e2_independent_validation as validation,
)
from Tools.core_freeze.e2_contract_boundaries.run_e2_development import (
    load_json,
)


class V11Cf04E2IndependentValidationOpeningTests(unittest.TestCase):
    def test_opening_package_excludes_held_out_task_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "opening"
            report = opening.build_package(output_dir)
            self.assertEqual(report["status"], "prepared_not_authorized")
            self.assertFalse(
                report["held_out_task_content_copied_into_opening"]
            )
            self.assertFalse(
                report["held_out_task_content_read_by_builder"]
            )
            self.assertFalse(report["external_api_execution_authorized"])
            self.assertEqual(report["external_api_calls"], 0)
            self.assertFalse(
                (output_dir / "e2_validation_tasks_v1.json").exists()
            )

    def test_static_bindings_and_frozen_cell_count(self):
        config = load_json(validation.CONFIG_PATH)
        validation.validate_static_bindings(config)
        self.assertEqual(config["task_count"], 40)
        self.assertEqual(config["condition_count"], 2)
        self.assertEqual(config["model_run_repeats"], 1)
        self.assertEqual(config["authorized_model_cell_count"], 80)
        self.assertFalse(config["gold_labels_sent"])
        self.assertFalse(config["mutation_history_sent"])

    def test_runner_fails_before_held_out_tasks_are_read(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_authorization = Path(temp_dir) / "missing_auth.json"
            missing_tasks = Path(temp_dir) / "must_not_be_read.json"
            with patch.object(
                validation,
                "AUTHORIZATION_PATH",
                missing_authorization,
            ), patch.object(validation, "TASKS_PATH", missing_tasks):
                with self.assertRaisesRegex(
                    FileNotFoundError,
                    "authorization is pending",
                ):
                    validation.load_authorized_inputs()

    def test_authorization_contract_binds_runner_and_both_prompts(self):
        config = load_json(validation.CONFIG_PATH)
        expected = validation.expected_authorization(config)
        self.assertEqual(
            expected["decision"],
            "authorized_to_execute_e2_independent_validation_v1",
        )
        self.assertEqual(expected["authorized_model_cell_count"], 80)
        self.assertEqual(
            expected["validation_dataset_access"],
            "authorized_once",
        )
        self.assertEqual(len(expected["runner_sha256"]), 64)
        self.assertEqual(len(expected["baseline_prompt_sha256"]), 64)
        self.assertEqual(len(expected["hybrid_prompt_sha256"]), 64)

    def test_summary_uses_paired_descriptive_differences(self):
        records = [
            {
                "task_id": "T1",
                "condition": "flags_only_v1_1",
                "status": "completed",
                "expected_flags": ["missing_parameter"],
                "expected_action": "clarify",
                "predicted_flags": [],
                "flags_exact": False,
                "predicted_action": "call",
                "action_correct": False,
            },
            {
                "task_id": "T1",
                "condition": "hybrid_semantic_v1_4",
                "status": "completed",
                "expected_flags": ["missing_parameter"],
                "expected_action": "clarify",
                "merged_flags": ["missing_parameter"],
                "merged_flags_exact": True,
                "predicted_action": "clarify",
                "action_correct": True,
            },
            {
                "task_id": "T2",
                "condition": "flags_only_v1_1",
                "status": "completed",
                "expected_flags": [],
                "expected_action": "call",
                "predicted_flags": [],
                "flags_exact": True,
                "predicted_action": "call",
                "action_correct": True,
            },
            {
                "task_id": "T2",
                "condition": "hybrid_semantic_v1_4",
                "status": "completed",
                "expected_flags": [],
                "expected_action": "call",
                "merged_flags": [],
                "merged_flags_exact": True,
                "predicted_action": "call",
                "action_correct": True,
            },
        ]
        policy = {"flags": ["missing_parameter"]}
        summary = validation.summarize(records, policy)
        self.assertEqual(
            summary["paired_descriptive_differences"][
                "hybrid_minus_baseline_flags_exact"
            ],
            1,
        )
        self.assertEqual(
            summary["paired_descriptive_differences"][
                "hybrid_minus_baseline_action_correct"
            ],
            1,
        )
        self.assertFalse(summary["confirmatory_inference_allowed"])


if __name__ == "__main__":
    unittest.main()
