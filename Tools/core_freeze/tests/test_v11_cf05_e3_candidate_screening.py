import copy
import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.e3_routing import screen_e3_source_candidates as screener


class V11Cf05E3CandidateScreeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = screener.load_json(screener.POLICY_PATH)
        cls.result = screener.screen(cls.policy)

    def test_screening_covers_all_candidates_in_three_nonfinal_lanes(self):
        summary = self.result["summary"]
        self.assertEqual(summary["candidate_count"], 20)
        self.assertEqual(
            summary["screening_lane_counts"],
            {
                "contract_draft_queue": 12,
                "equivalence_test_required": 5,
                "screened_out_before_fixture": 3,
            },
        )
        self.assertEqual(summary["accepted_candidate_count"], 0)
        self.assertEqual(summary["catalog_increment_count"], 0)
        self.assertEqual(summary["equivalence_test_complete_count"], 0)
        self.assertEqual(summary["independence_review_complete_count"], 0)
        self.assertEqual(summary["relation_fixture_complete_count"], 0)

    def test_contract_draft_queue_is_target_specific(self):
        summary = self.result["summary"]
        self.assertEqual(
            summary["contract_draft_queue_count_by_target"],
            {"A001": 1, "A002": 3, "A003": 2, "A004": 4, "B019": 2},
        )
        self.assertEqual(summary["preliminary_alias_name_pass_count"], 9)
        self.assertEqual(
            summary["preliminary_alias_name_pass_count_by_target"],
            {"A002": 3, "A003": 2, "A004": 4},
        )

    def test_duplicate_accessor_and_plotter_are_screened_out(self):
        rows = {
            row["provisional_candidate_id"]: row
            for row in self.result["screening_matrix"]["rows"]
        }
        self.assertEqual(rows["SRC-PYCAL-001"]["screening_lane"], "screened_out_before_fixture")
        self.assertIn("B023", rows["SRC-PYCAL-001"]["existing_catalog_matches"])
        self.assertEqual(rows["SRC-PYCAL-002"]["independence_class"], "dependent_result_accessor")
        self.assertEqual(rows["SRC-PYCAL-005"]["independence_class"], "presentation_only_postprocessor")

    def test_equivalence_risk_never_becomes_unacceptable_neighbor(self):
        rows = self.result["screening_matrix"]["rows"]
        equivalence_rows = [
            row for row in rows if row["screening_lane"] == "equivalence_test_required"
        ]
        self.assertEqual(len(equivalence_rows), 5)
        self.assertTrue(all(not row["may_enter_contract_draft"] for row in equivalence_rows))
        self.assertTrue(all(not row["may_fill_relation_slot"] for row in equivalence_rows))
        self.assertTrue(
            all(row["semantic_equivalence_test_passed"] is None for row in equivalence_rows)
        )

    def test_no_preliminary_result_reduces_frozen_gaps(self):
        summary = self.result["summary"]
        self.assertEqual(summary["filled_relation_slot_count"], 0)
        self.assertEqual(summary["remaining_lexical_gap"], 30)
        self.assertEqual(summary["remaining_contract_mismatch_gap"], 40)
        self.assertEqual(summary["external_api_calls"], 0)
        self.assertFalse(summary["formal_pool_generation_allowed"])
        self.assertFalse(summary["core_frozen"])

    def test_missing_decision_is_rejected(self):
        invalid = copy.deepcopy(self.policy)
        invalid["decisions"].pop()
        with self.assertRaisesRegex(ValueError, "cover the source registry exactly"):
            screener.screen(invalid)

    def test_output_manifest_is_complete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            screener.build_outputs(output_dir)
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["artifact_count"], 4)
            for artifact in manifest["artifacts"]:
                path = output_dir / artifact["filename"]
                self.assertTrue(path.is_file())
                self.assertEqual(screener.sha256_file(path), artifact["sha256"])


if __name__ == "__main__":
    unittest.main()
