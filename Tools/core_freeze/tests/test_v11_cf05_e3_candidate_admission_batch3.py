import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from Tools.core_freeze.e3_routing import decide_e3_candidate_admission_batch3 as decider


class V11Cf05E3CandidateAdmissionBatch3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = decider.load_json(decider.CONFIG_PATH)
        cls.result = decider.decide(cls.config)
        cls.report = cls.result["report"]

    def test_bound_manifests_and_artifacts_are_immutable(self):
        for row in self.config["bindings"]:
            decider.validate_manifest(decider.WORKSPACE / row["path"], row["sha256"])

    def test_exactly_eight_candidates_enter_one_relation_each(self):
        admitted = self.result["decisions"]["admitted"]
        self.assertEqual([row["candidate_tool_id"] for row in admitted], [f"E3C{number:03d}" for number in range(18, 26)])
        self.assertEqual(len({row["candidate_tool_id"] for row in admitted}), 8)
        self.assertTrue(all(row["target_tool_id"] == "A003" for row in admitted))
        self.assertTrue(all(row["relation_registry_admitted"] for row in admitted))
        self.assertTrue(all(not row["formal_pool_inclusion"] for row in admitted))

    def test_admitted_dose_is_two_lexical_and_six_mismatch(self):
        counts = Counter(row["relation_type"] for row in self.result["decisions"]["admitted"])
        self.assertEqual(counts, Counter({"contract_mismatch": 6, "lexical": 2}))
        self.assertEqual(self.report["lexical_relation_admission_count"], 2)
        self.assertEqual(self.report["contract_mismatch_relation_admission_count"], 6)

    def test_combined_registry_carries_prior_relations_without_duplicates(self):
        combined = self.result["combined_relations"]
        self.assertEqual(combined["relation_count"], 21)
        self.assertEqual(len(combined["relations"]), len({row["candidate_tool_id"] for row in combined["relations"]}))
        self.assertEqual(combined["formal_pool_inclusion_count"], 0)

    def test_a003_reaches_paired_eight_and_global_gaps_recompute(self):
        gap = self.result["gap"]
        a003 = next(row for row in gap["rows"] if row["target_tool_id"] == "A003")
        self.assertEqual(a003["lexical_count_before"], 6)
        self.assertEqual(a003["lexical_admitted"], 2)
        self.assertEqual(a003["lexical_count_after"], 8)
        self.assertEqual(a003["contract_mismatch_count_before"], 2)
        self.assertEqual(a003["contract_mismatch_admitted"], 6)
        self.assertEqual(a003["contract_mismatch_count_after"], 8)
        self.assertTrue(a003["paired_8_ready_after"])
        self.assertEqual(gap["paired_8_ready_target_ids"], ["A003"])
        self.assertEqual(gap["lexical_gap_after"], 22)
        self.assertEqual(gap["contract_mismatch_gap_after"], 27)

    def test_acceptable_registry_and_formal_state_remain_unchanged(self):
        self.assertTrue(self.report["acceptable_tools_registry_unchanged"])
        self.assertEqual(self.report["formal_catalog_size"], 120)
        self.assertEqual(self.report["scientific_function_catalog_increment_count"], 0)
        self.assertEqual(self.report["formal_pool_inclusion_count"], 0)
        self.assertEqual(self.report["external_api_calls"], 0)
        self.assertFalse(self.report["formal_pool_generation_allowed"])
        self.assertFalse(self.report["confirmatory_inference_allowed"])
        self.assertEqual(self.report["cf05_status"], "in_progress")
        self.assertFalse(self.report["core_frozen"])

    def test_policy_mutation_is_rejected(self):
        invalid = copy.deepcopy(self.config)
        invalid["formal_catalog_mutation_allowed"] = True
        with self.assertRaisesRegex(ValueError, "must remain false"):
            decider.decide(invalid)

    def test_fresh_output_has_complete_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "admission"
            report = decider.build_outputs(output_dir)
            self.assertEqual(report, self.report)
            manifest = json.loads((output_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifact_count"], 6)
            for row in manifest["artifacts"]:
                path = output_dir / row["filename"]
                self.assertEqual(decider.sha256_file(path), row["sha256"])
                self.assertEqual(path.stat().st_size, row["bytes"])


if __name__ == "__main__":
    unittest.main()
