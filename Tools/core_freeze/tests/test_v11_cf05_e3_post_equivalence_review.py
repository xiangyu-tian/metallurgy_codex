import copy
import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.e3_routing import build_e3_post_equivalence_review as builder


class V11Cf05E3PostEquivalenceReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = builder.load_json(builder.CONFIG_PATH)
        cls.result = builder.build_review(cls.config)

    def test_pint_is_implementation_independent_but_not_a_new_scientific_function(self):
        review = self.result["independence_review"]
        self.assertEqual(review["provisional_candidate_id"], "SRC-PINT-001")
        self.assertTrue(review["implementation_provider_distinct"])
        self.assertFalse(review["scientific_function_distinct"])
        self.assertTrue(review["acceptable_tools_candidate_over_frozen_scope"])
        self.assertFalse(review["formal_acceptable_tools_admission"])
        self.assertFalse(review["catalog_increment_allowed"])
        self.assertTrue(
            all(not row["forbidden_import_hits"] for row in review["target_runtime_sources"])
        )

    def test_four_observed_mismatches_become_development_fixture_candidates(self):
        package = self.result["fixture_package"]
        self.assertEqual(package["fixture_count"], 4)
        self.assertEqual(
            {row["provisional_candidate_id"] for row in package["fixtures"]},
            {"SRC-PMG-001", "SRC-RDKIT-004", "SRC-PMG-002", "SRC-PMG-003"},
        )
        for row in package["fixtures"]:
            self.assertTrue(row["target_reference_behavior_bound"])
            self.assertTrue(row["candidate_mismatch_observed"])
            self.assertEqual(row["fixture_status"], "development_fixture_candidate_not_held_out")
            self.assertFalse(row["formal_neighbor_admission"])

    def test_review_does_not_change_formal_counts(self):
        report = self.result["report"]
        self.assertEqual(report["acceptable_tools_candidate_count"], 1)
        self.assertEqual(report["formal_acceptable_tools_admission_count"], 0)
        self.assertEqual(report["held_out_fixture_count"], 0)
        self.assertEqual(report["formal_neighbor_admission_count"], 0)
        self.assertEqual(report["catalog_increment_count"], 0)
        self.assertEqual(report["filled_relation_slot_count"], 0)
        self.assertEqual(report["remaining_lexical_gap"], 30)
        self.assertEqual(report["remaining_contract_mismatch_gap"], 40)
        self.assertEqual(report["external_api_calls"], 0)
        self.assertFalse(report["formal_pool_generation_allowed"])
        self.assertFalse(report["confirmatory_inference_allowed"])
        self.assertFalse(report["core_frozen"])

    def test_a_passing_case_cannot_be_selected_as_mismatch_fixture(self):
        invalid = copy.deepcopy(self.config)
        invalid["fixture_selections"][0]["reference_case_id"] = "VC-A002-N01"
        with self.assertRaisesRegex(ValueError, "fixture must bind an observed mismatch"):
            builder.build_review(invalid)

    def test_output_manifest_is_complete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "review"
            builder.build_outputs(output_dir)
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["artifact_count"], 4)
            for artifact in manifest["artifacts"]:
                path = output_dir / artifact["filename"]
                self.assertEqual(builder.sha256_file(path), artifact["sha256"])
                self.assertEqual(path.stat().st_size, artifact["bytes"])


if __name__ == "__main__":
    unittest.main()
