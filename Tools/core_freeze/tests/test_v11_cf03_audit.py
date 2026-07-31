import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.audit_v11_cf03 import (
    PROJECT_ROOT,
    audit_e1b_run,
    audit_split_isolation,
    file_hash,
    run_audit,
    BENEFIT_RUN_DIR,
    GATE_RUN_DIR,
)


class V11Cf03AuditTests(unittest.TestCase):
    def test_e1b_runs_have_complete_three_repeat_pairs(self):
        benefit, _ = audit_e1b_run(BENEFIT_RUN_DIR, "benefit_estimation")
        gate, _ = audit_e1b_run(GATE_RUN_DIR, "gate_evaluation")
        self.assertEqual(benefit["status"], "passed")
        self.assertEqual(gate["status"], "passed")
        self.assertEqual(benefit["model_run_repeats"], [1, 2, 3])
        self.assertEqual(gate["model_run_repeats"], [1, 2, 3])
        self.assertEqual(benefit["paired_repeat_count"], 135)
        self.assertEqual(gate["paired_repeat_count"], 81)

    def test_benefit_and_gate_identifiers_are_disjoint(self):
        _, benefit = audit_e1b_run(
            BENEFIT_RUN_DIR, "benefit_estimation"
        )
        _, gate = audit_e1b_run(GATE_RUN_DIR, "gate_evaluation")
        result = audit_split_isolation(benefit, gate)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(
            result["overlaps"],
            {"task_id": [], "task_pair_id": [], "base_task_group_id": []},
        )

    def test_candidate_package_preserves_confirmatory_boundary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "cf03"
            report = run_audit(output_dir)
            self.assertEqual(report["status"], "in_progress")
            self.assertEqual(report["candidate_evidence_status"], "passed")
            self.assertFalse(
                report["pilot_results_promoted_to_confirmatory"]
            )
            self.assertFalse(report["tool_benefit_written_back_to_base_truth"])
            self.assertFalse(report["core_frozen"])

            registry = json.loads(
                (output_dir / "benefit_evidence_registry.json").read_text(
                    encoding="utf-8"
                )
            )
            roles = {
                row["evidence_role"]: row for row in registry["datasets"]
            }
            self.assertTrue(
                roles["benefit_calibration"][
                    "eligible_for_pilot_effect_estimation"
                ]
            )
            self.assertTrue(
                roles["gate_evaluation"][
                    "eligible_for_gate_performance_claim"
                ]
            )
            self.assertFalse(
                roles["mechanism_evaluation_secondary"][
                    "eligible_for_e1b_primary_benefit_estimate"
                ]
            )
            self.assertFalse(
                registry["anti_leakage_policy"][
                    "pilot_result_written_back_to_base_truth"
                ]
            )

            power_input = json.loads(
                (output_dir / "power_input.json").read_text(
                    encoding="utf-8"
                )
            )
            constraints = power_input["analysis_constraints"]
            self.assertTrue(constraints["independence_unit_is_not_paired_repeat"])
            self.assertEqual(
                constraints["cluster_unit"], "base_task_group_id"
            )
            self.assertFalse(constraints["formal_repeat_count_frozen"])
            self.assertFalse(constraints["formal_sample_size_frozen"])

    def test_manifest_hashes_all_candidate_and_source_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "cf03"
            run_audit(output_dir)
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            for row in manifest["artifacts"]:
                artifact = output_dir / row["filename"]
                self.assertTrue(artifact.is_file())
                self.assertEqual(file_hash(artifact), row["sha256"])
            for row in manifest["source_artifacts"]:
                source = PROJECT_ROOT / row["filename"]
                self.assertTrue(source.is_file())
                self.assertEqual(file_hash(source), row["sha256"])

    def test_audit_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "cf03"
            run_audit(output_dir)
            with self.assertRaises(FileExistsError):
                run_audit(output_dir)


if __name__ == "__main__":
    unittest.main()
