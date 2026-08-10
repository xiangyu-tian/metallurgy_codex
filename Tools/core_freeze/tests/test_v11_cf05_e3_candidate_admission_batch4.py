import copy
import json
import shutil
import unittest
import uuid
from collections import Counter

from Tools.core_freeze.e3_routing import decide_e3_candidate_admission_batch4 as decider


class V11Cf05E3CandidateAdmissionBatch4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = decider.load_json(decider.CONFIG_PATH)
        cls.result = decider.decide(cls.config)
        cls.report = cls.result["report"]

    def test_two_candidates_enter_one_nonformal_relation_each(self):
        admitted = self.result["decisions"]["admitted"]
        self.assertEqual([row["candidate_tool_id"] for row in admitted], ["E3C026", "E3C027"])
        self.assertEqual(Counter(row["relation_type"] for row in admitted), Counter({"lexical": 1, "contract_mismatch": 1}))
        self.assertTrue(all(row["relation_registry_admitted"] for row in admitted))
        self.assertTrue(all(not row["formal_pool_inclusion"] for row in admitted))

    def test_a004_reaches_paired_four_but_not_paired_eight(self):
        gap = self.result["gap"]
        a004 = next(row for row in gap["rows"] if row["target_tool_id"] == "A004")
        self.assertEqual((a004["lexical_count_before"], a004["lexical_count_after"]), (3, 4))
        self.assertEqual((a004["contract_mismatch_count_before"], a004["contract_mismatch_count_after"]), (3, 4))
        self.assertTrue(a004["paired_4_ready_after"])
        self.assertFalse(a004["paired_8_ready_after"])
        self.assertEqual(gap["paired_4_ready_target_ids"], ["A003", "A004"])
        self.assertEqual(gap["paired_8_ready_target_ids"], ["A003"])

    def test_combined_registry_and_global_gaps_recompute(self):
        self.assertEqual(self.result["combined_relations"]["relation_count"], 23)
        self.assertEqual(self.result["gap"]["lexical_gap_after"], 21)
        self.assertEqual(self.result["gap"]["contract_mismatch_gap_after"], 26)

    def test_formal_and_acceptable_state_remain_unchanged(self):
        self.assertTrue(self.report["acceptable_tools_registry_unchanged"])
        self.assertEqual(self.report["formal_catalog_size"], 120)
        self.assertEqual(self.report["scientific_function_catalog_increment_count"], 0)
        self.assertEqual(self.report["external_api_calls"], 0)
        self.assertFalse(self.report["formal_pool_generation_allowed"])
        self.assertFalse(self.report["confirmatory_inference_allowed"])
        self.assertEqual(self.report["cf05_status"], "in_progress")

    def test_policy_mutation_is_rejected(self):
        invalid = copy.deepcopy(self.config)
        invalid["formal_catalog_mutation_allowed"] = True
        with self.assertRaisesRegex(ValueError, "must remain false"):
            decider.decide(invalid)

    def test_manifest_and_fresh_output_are_complete(self):
        output_dir = decider.WORKSPACE / "outputs" / f".batch4-admission-test-{uuid.uuid4().hex}"
        try:
            self.assertEqual(decider.build_outputs(output_dir), self.report)
            manifest = json.loads((output_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifact_count"], 6)
            for row in manifest["artifacts"]:
                self.assertEqual(decider.sha256_file(output_dir / row["filename"]), row["sha256"])
        finally:
            if output_dir.exists():
                shutil.rmtree(output_dir)


if __name__ == "__main__":
    unittest.main()
