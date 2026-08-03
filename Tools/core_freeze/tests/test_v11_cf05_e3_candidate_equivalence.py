import json
import unittest
from pathlib import Path

from Tools.core_freeze.e3_routing import run_e3_candidate_equivalence as runner


OUTPUT_DIR = (
    runner.WORKSPACE
    / "outputs"
    / "v11_cf05_e3_equivalence_batch1_r1_20260803"
)


def load_output(filename: str):
    return json.loads((OUTPUT_DIR / filename).read_text(encoding="utf-8"))


class V11Cf05E3CandidateEquivalenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = runner.load_json(runner.CONFIG_PATH)
        cls.report = load_output("equivalence_run_report.json")
        cls.summary = load_output("equivalence_candidate_summary.json")
        cls.case_results = load_output("equivalence_case_results.json")
        cls.environment = load_output("environment_lock_verification.json")

    def test_execution_inputs_are_bound_by_hash(self):
        for path_key, hash_key in (
            ("equivalence_plan_path", "equivalence_plan_sha256"),
            ("reference_cases_path", "reference_cases_sha256"),
            ("requirements_lock_path", "requirements_lock_sha256"),
        ):
            path = runner.WORKSPACE / self.config[path_key]
            self.assertEqual(runner.sha256_file(path), self.config[hash_key])

    def test_isolated_environment_was_fully_locked(self):
        self.assertTrue(self.environment["environment_verification_passed"])
        self.assertEqual(self.environment["python_version"], "3.11.15")
        self.assertEqual(self.environment["locked_distribution_count"], 59)
        self.assertEqual(self.environment["installed_distribution_count"], 59)
        self.assertEqual(self.environment["missing_distributions"], [])
        self.assertEqual(self.environment["unexpected_distributions"], [])
        self.assertEqual(self.environment["version_mismatches"], [])

    def test_five_candidates_expand_to_twenty_five_comparisons(self):
        rows = self.case_results["rows"]
        self.assertEqual(self.summary["candidate_count"], 5)
        self.assertEqual(self.case_results["case_count"], 25)
        self.assertEqual(len(rows), 25)
        self.assertEqual(len({row["reference_case_id"] for row in rows}), 21)
        self.assertEqual(self.report["comparison_pass_count"], 18)
        self.assertEqual(self.report["comparison_fail_count"], 7)

    def test_candidate_classifications_match_observed_cases(self):
        candidates = {
            row["provisional_candidate_id"]: row
            for row in self.summary["candidates"]
        }
        self.assertEqual(
            candidates["SRC-PINT-001"]["equivalence_classification"],
            "exact_equivalent_over_frozen_scope",
        )
        self.assertTrue(candidates["SRC-PINT-001"]["may_enter_acceptable_tool_set"])
        self.assertEqual(
            candidates["SRC-PMG-003"]["equivalence_classification"],
            "partial_equivalent_overlap_only",
        )
        self.assertTrue(candidates["SRC-PMG-003"]["conditional_acceptable_subdomain_only"])
        for candidate_id in ("SRC-PMG-001", "SRC-RDKIT-004", "SRC-PMG-002"):
            self.assertEqual(
                candidates[candidate_id]["equivalence_classification"],
                "not_equivalent_over_frozen_scope",
            )

    def test_failures_preserve_boundary_and_numeric_mismatches(self):
        failures = {
            (row["provisional_candidate_id"], row["reference_case_id"]): row
            for row in self.case_results["rows"]
            if not row["comparison_pass"]
        }
        self.assertEqual(len(failures), 7)
        self.assertEqual(
            failures[("SRC-PMG-001", "VC-A002-B03")]["comparison_basis"],
            "success_failure_outcome_mismatch",
        )
        self.assertEqual(
            failures[("SRC-RDKIT-004", "VC-A003-B01")]["comparison_basis"],
            "adapter_unavailable",
        )
        self.assertIn(("SRC-PMG-002", "VC-A003-N01"), failures)
        self.assertIn(("SRC-PMG-003", "VC-A004-B01"), failures)

    def test_run_does_not_admit_formal_tools_or_reduce_gaps(self):
        self.assertEqual(self.report["acceptable_tool_candidate_count"], 1)
        self.assertEqual(self.report["conditional_subdomain_candidate_count"], 1)
        self.assertEqual(self.report["unacceptable_neighbor_admission_count"], 0)
        self.assertEqual(self.report["catalog_increment_count"], 0)
        self.assertEqual(self.report["filled_relation_slot_count"], 0)
        self.assertEqual(self.report["remaining_lexical_gap"], 30)
        self.assertEqual(self.report["remaining_contract_mismatch_gap"], 40)
        self.assertEqual(self.report["external_api_calls"], 0)
        self.assertFalse(self.report["confirmatory_inference_allowed"])
        self.assertFalse(self.report["formal_pool_generation_allowed"])
        self.assertFalse(self.report["core_frozen"])

    def test_manifest_covers_every_formal_artifact(self):
        manifest = load_output("artifact_manifest.json")
        expected = {
            "environment_lock_verification.json",
            "equivalence_candidate_summary.json",
            "equivalence_case_results.json",
            "equivalence_execution_config_snapshot.json",
            "equivalence_run_report.json",
        }
        self.assertEqual(manifest["artifact_count"], len(expected))
        self.assertEqual({row["filename"] for row in manifest["artifacts"]}, expected)
        for artifact in manifest["artifacts"]:
            path = OUTPUT_DIR / artifact["filename"]
            self.assertEqual(runner.sha256_file(path), artifact["sha256"])
            self.assertEqual(path.stat().st_size, artifact["bytes"])


if __name__ == "__main__":
    unittest.main()
