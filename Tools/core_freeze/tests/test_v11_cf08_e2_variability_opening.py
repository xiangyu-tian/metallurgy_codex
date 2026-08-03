import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Tools.core_freeze.e2_contract_boundaries import (
    analyze_e2_variability_r1_r3 as analysis,
    build_e2_variability_r2_r3_opening as opening,
    run_e2_variability_r2_r3 as runner,
)
from Tools.core_freeze.e2_contract_boundaries.run_e2_development import (
    load_json,
)


def _record(task_id, condition, repeat_id, *, correct=True):
    common = {
        "cell_id": f"{task_id}::{condition}::R{repeat_id}",
        "task_id": task_id,
        "condition": condition,
        "model_run_repeat": repeat_id,
        "status": "completed",
        "expected_flags": ["ambiguous_parameter"],
        "expected_action": "clarify",
        "predicted_action": "clarify" if correct else "call",
        "action_correct": correct,
    }
    if condition == "flags_only_v1_1":
        return {
            **common,
            "predicted_flags": ["ambiguous_parameter"] if correct else [],
            "flags_exact": correct,
        }
    return {
        **common,
        "merged_flags": ["ambiguous_parameter"] if correct else [],
        "merged_flags_exact": correct,
    }


class V11Cf08E2VariabilityOpeningTests(unittest.TestCase):
    def test_static_bindings_freeze_r2_r3_and_160_cells(self):
        config = load_json(runner.CONFIG_PATH)
        runner.validate_static_bindings(config)
        self.assertEqual(config["repeat_ids"], [2, 3])
        self.assertEqual(config["authorized_model_cell_count"], 160)
        self.assertFalse(config["repeat_units_are_independent_tasks"])
        self.assertFalse(config["post_validation_policy_revision_allowed"])

    def test_runner_fails_before_opened_tasks_are_read(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_auth = Path(temp_dir) / "missing_auth.json"
            missing_tasks = Path(temp_dir) / "must_not_be_read.json"
            with patch.object(runner, "AUTHORIZATION_PATH", missing_auth), patch.object(
                runner.base,
                "TASKS_PATH",
                missing_tasks,
            ):
                with self.assertRaisesRegex(
                    FileNotFoundError,
                    "authorization is pending",
                ):
                    runner.load_authorized_inputs()

    def test_authorization_contract_binds_repeats_and_r1_evidence(self):
        config = load_json(runner.CONFIG_PATH)
        expected = runner.expected_authorization(config)
        self.assertEqual(expected["authorized_repeat_ids"], [2, 3])
        self.assertEqual(expected["authorized_model_cell_count"], 160)
        self.assertEqual(
            expected["opened_validation_reuse"],
            "variability_estimation_only",
        )
        self.assertEqual(len(expected["r1_run_manifest_sha256"]), 64)
        self.assertEqual(len(expected["runner_sha256"]), 64)

    def test_opening_package_excludes_task_content_and_api_calls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "opening"
            report = opening.build_package(output_dir)
            self.assertEqual(report["status"], "prepared_not_authorized")
            self.assertEqual(report["model_cell_count"], 160)
            self.assertFalse(report["held_out_task_content_read_by_builder"])
            self.assertFalse(report["held_out_task_content_copied_into_opening"])
            self.assertFalse(report["external_api_execution_authorized"])
            self.assertEqual(report["external_api_calls"], 0)
            self.assertFalse(
                (output_dir / "e2_validation_tasks_v1.json").exists()
            )

    def test_combined_analysis_keeps_repeats_clustered_by_task(self):
        r1_records = []
        extra_records = []
        for index in range(40):
            task_id = f"T{index:02d}"
            for condition in ("flags_only_v1_1", "hybrid_semantic_v1_4"):
                r1_records.append(_record(task_id, condition, 1))
                extra_records.append(
                    _record(
                        task_id,
                        condition,
                        2,
                        correct=not (
                            index == 0 and condition == "flags_only_v1_1"
                        ),
                    )
                )
                extra_records.append(_record(task_id, condition, 3))
        result = analysis.analyze_variability(r1_records, extra_records)
        baseline = result["stability_summary"]["flags_only_v1_1"]
        hybrid = result["stability_summary"]["hybrid_semantic_v1_4"]
        self.assertEqual(baseline["flag_prediction_stable_count"], 39)
        self.assertEqual(hybrid["flag_prediction_stable_count"], 40)
        self.assertFalse(
            result["analysis_policy"]["repeat_units_are_independent_tasks"]
        )
        self.assertTrue(result["analysis_policy"]["task_is_resampling_cluster"])


if __name__ == "__main__":
    unittest.main()
