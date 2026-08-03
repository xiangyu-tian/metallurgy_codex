import copy
import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.e3_routing import decide_e3_candidate_admission as decider


class V11Cf05E3CandidateAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = decider.load_json(decider.CONFIG_PATH)
        cls.result = decider.decide(cls.config)

    def test_all_bound_manifests_and_protocol_are_hash_locked(self):
        for binding in self.config["bindings"]:
            path = decider.WORKSPACE / binding["path"]
            self.assertEqual(decider.sha256_file(path), binding["sha256"])

    def test_pint_enters_acceptable_registry_without_catalog_increment(self):
        decision = self.result["decisions"]["acceptable_decision"]
        self.assertEqual(decision["candidate_tool_id"], "E3C001")
        self.assertEqual(decision["target_tool_id"], "A001")
        self.assertTrue(decision["acceptable_tools_registry_admitted"])
        self.assertEqual(decision["decision"], "admit_to_task_acceptable_tools_registry")
        self.assertFalse(decision["counts_as_new_scientific_function"])
        self.assertFalse(decision["counts_toward_formal_catalog_size"])
        self.assertFalse(decision["formal_pool_inclusion"])
        acceptable_set = self.result["acceptable_registry"]["sets"][0]
        self.assertEqual(acceptable_set["acceptable_tool_ids"], ["A001", "E3C001"])

    def test_four_candidates_enter_exactly_one_relation_registry_slot(self):
        rows = self.result["relation_registry"]["relations"]
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({row["candidate_tool_id"] for row in rows}), 4)
        self.assertEqual(
            {(row["candidate_tool_id"], row["target_tool_id"], row["relation_type"]) for row in rows},
            {
                ("E3C002", "A002", "contract_mismatch"),
                ("E3C003", "A003", "lexical"),
                ("E3C004", "A003", "contract_mismatch"),
                ("E3C005", "A004", "contract_mismatch"),
            },
        )
        self.assertTrue(all(row["relation_registry_admitted"] for row in rows))
        self.assertTrue(all(not row["formal_pool_inclusion"] for row in rows))

    def test_gap_recalculation_uses_source_requirement_matrix(self):
        gap = self.result["gap_matrix"]
        self.assertEqual(gap["lexical_gap_before"], 30)
        self.assertEqual(gap["lexical_admitted"], 1)
        self.assertEqual(gap["lexical_gap_after"], 29)
        self.assertEqual(gap["contract_mismatch_gap_before"], 40)
        self.assertEqual(gap["contract_mismatch_admitted"], 3)
        self.assertEqual(gap["contract_mismatch_gap_after"], 37)
        a003 = next(row for row in gap["rows"] if row["target_tool_id"] == "A003")
        self.assertEqual(a003["lexical_count_after"], 5)
        self.assertEqual(a003["contract_mismatch_count_after"], 1)

    def test_admission_does_not_generate_formal_catalog_or_pool(self):
        report = self.result["report"]
        self.assertEqual(report["acceptable_tools_registry_admission_count"], 1)
        self.assertEqual(report["neighbor_relation_registry_admission_count"], 4)
        self.assertEqual(report["scientific_function_catalog_increment_count"], 0)
        self.assertEqual(report["formal_catalog_size"], 120)
        self.assertEqual(report["formal_pool_inclusion_count"], 0)
        self.assertEqual(report["external_api_calls"], 0)
        self.assertFalse(report["formal_pool_generation_allowed"])
        self.assertFalse(report["confirmatory_inference_allowed"])
        self.assertFalse(report["core_frozen"])

    def test_disallowing_a_required_relation_rejects_admission(self):
        invalid = copy.deepcopy(self.config)
        invalid["allowed_neighbor_relation_types"] = ["lexical"]
        with self.assertRaisesRegex(ValueError, "candidate admissions failed"):
            decider.decide(invalid)

    def test_output_manifest_is_complete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "admission"
            decider.build_outputs(output_dir)
            manifest = json.loads((output_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifact_count"], 6)
            for artifact in manifest["artifacts"]:
                path = output_dir / artifact["filename"]
                self.assertEqual(decider.sha256_file(path), artifact["sha256"])
                self.assertEqual(path.stat().st_size, artifact["bytes"])


if __name__ == "__main__":
    unittest.main()
