import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.finalize_v11_cf08_cf09 import (
    APPROVAL_PATH,
    CF08_REPORT_PATH,
    PROJECT_ROOT,
    file_hash,
    load_json,
    run_finalization,
    validate_approval,
)


class V11Cf08Cf09FinalizeTests(unittest.TestCase):
    def test_approval_is_bound_to_candidate_hashes_and_parameters(self):
        report = load_json(CF08_REPORT_PATH)
        approval = load_json(APPROVAL_PATH)
        self.assertEqual(validate_approval(report, approval), [])
        self.assertEqual(
            approval["approved_parameters"]["base_task_groups"], 120
        )
        self.assertEqual(
            approval["approved_parameters"]["model_run_repeats"], 3
        )

    def test_tampered_parameter_is_rejected(self):
        report = load_json(CF08_REPORT_PATH)
        approval = load_json(APPROVAL_PATH)
        approval["approved_parameters"]["model_run_repeats"] = 4
        errors = validate_approval(report, approval)
        self.assertTrue(
            any("model_run_repeats" in error for error in errors)
        )

    def test_finalization_passes_cf03_without_overclaiming_cf08_cf09(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "final"
            result = run_finalization(output_dir)
            self.assertEqual(
                result["status_updates"]["cf03"]["overall"], "passed"
            )
            self.assertEqual(
                result["status_updates"]["cf08"]["overall"], "in_progress"
            )
            self.assertEqual(
                result["status_updates"]["cf09"]["overall"], "in_progress"
            )
            self.assertFalse(result["approval_is_cryptographic_signature"])
            self.assertFalse(result["core_frozen"])

            coverage = json.loads(
                (output_dir / "cf09_coverage_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(coverage["approved_experiment_count"], 1)
            self.assertEqual(coverage["required_experiment_count"], 4)
            self.assertEqual(coverage["cf09_status"], "in_progress")

    def test_manifest_binds_outputs_and_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "final"
            run_finalization(output_dir)
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            for row in manifest["artifacts"]:
                artifact = output_dir / row["filename"]
                self.assertEqual(file_hash(artifact), row["sha256"])
            for row in manifest["source_artifacts"]:
                source = PROJECT_ROOT / row["filename"]
                self.assertEqual(file_hash(source), row["sha256"])

    def test_finalization_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "final"
            run_finalization(output_dir)
            with self.assertRaises(FileExistsError):
                run_finalization(output_dir)


if __name__ == "__main__":
    unittest.main()
