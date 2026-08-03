import copy
import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.e3_routing import decide_e3_candidate_admission_batch2 as decider


OUTPUT_DIR = decider.WORKSPACE / "outputs" / "v11_cf05_e3_candidate_admission_batch2_v1_20260803"


def load_output(filename: str):
    return json.loads((OUTPUT_DIR / filename).read_text(encoding="utf-8"))


class V11Cf05E3CandidateAdmissionBatch2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = decider.load_json(decider.CONFIG_PATH)
        cls.decisions = load_output("candidate_admission_decisions.json")
        cls.combined = load_output("combined_relation_evidence_registry.json")
        cls.gap = load_output("recalculated_gap_matrix.json")
        cls.report = load_output("candidate_admission_report.json")

    def test_bound_manifests_and_artifacts_are_immutable(self):
        for row in self.config["bindings"]:
            path = decider.WORKSPACE / row["path"]
            decider.validate_manifest(path, row["sha256"])

    def test_nine_candidates_enter_one_relation_each(self):
        admitted = self.decisions["admitted"]
        self.assertEqual(len(admitted), 9)
        self.assertEqual(len({row["candidate_tool_id"] for row in admitted}), 9)
        self.assertTrue(all(row["relation_registry_admitted"] for row in admitted))
        self.assertTrue(all(not row["formal_pool_inclusion"] for row in admitted))
        self.assertEqual(
            {row["relation_type"] for row in admitted},
            {"lexical", "contract_mismatch"},
        )

    def test_runtime_success_does_not_override_failed_relation_threshold(self):
        held = self.decisions["relation_held"]
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0]["candidate_tool_id"], "E3C007")
        self.assertTrue(held[0]["runtime_contract_passed"])
        self.assertFalse(held[0]["relation_registry_admitted"])

    def test_pycalphad_reservations_are_held_not_admitted(self):
        blocked = self.decisions["blocked"]
        self.assertEqual({row["candidate_tool_id"] for row in blocked}, {"E3C016", "E3C017"})
        self.assertTrue(all(row["decision"] == "hold_until_scientific_asset_frozen" for row in blocked))
        self.assertTrue(all(not row["relation_registry_admitted"] for row in blocked))

    def test_combined_registry_carries_first_batch_without_duplicates(self):
        rows = self.combined["relations"]
        self.assertEqual(self.combined["relation_count"], 13)
        self.assertEqual(len(rows), len({row["candidate_tool_id"] for row in rows}))
        self.assertEqual(
            {row["candidate_tool_id"] for row in rows},
            {f"E3C{number:03d}" for number in range(2, 16)} - {"E3C007"},
        )
        self.assertEqual(self.combined["formal_pool_inclusion_count"], 0)

    def test_gap_recalculation_starts_from_batch1(self):
        self.assertEqual(self.gap["lexical_gap_before"], 29)
        self.assertEqual(self.gap["lexical_admitted"], 5)
        self.assertEqual(self.gap["lexical_gap_after"], 24)
        self.assertEqual(self.gap["contract_mismatch_gap_before"], 37)
        self.assertEqual(self.gap["contract_mismatch_admitted"], 4)
        self.assertEqual(self.gap["contract_mismatch_gap_after"], 33)
        self.assertFalse(any(row["paired_8_ready_after"] for row in self.gap["rows"]))

    def test_no_formal_catalog_or_pool_mutation(self):
        self.assertEqual(self.report["formal_catalog_size"], 120)
        self.assertEqual(self.report["scientific_function_catalog_increment_count"], 0)
        self.assertEqual(self.report["formal_pool_inclusion_count"], 0)
        self.assertEqual(self.report["external_api_calls"], 0)
        self.assertFalse(self.report["formal_pool_generation_allowed"])
        self.assertFalse(self.report["confirmatory_inference_allowed"])
        self.assertFalse(self.report["core_frozen"])

    def test_policy_mutation_is_rejected(self):
        invalid = copy.deepcopy(self.config)
        invalid["formal_catalog_mutation_allowed"] = True
        with self.assertRaisesRegex(ValueError, "must remain false"):
            decider.decide(invalid)

    def test_output_manifest_is_complete(self):
        manifest = load_output("artifact_manifest.json")
        self.assertEqual(manifest["artifact_count"], 6)
        for row in manifest["artifacts"]:
            path = OUTPUT_DIR / row["filename"]
            self.assertEqual(decider.sha256_file(path), row["sha256"])
            self.assertEqual(path.stat().st_size, row["bytes"])

    def test_fresh_output_reproduces_decision(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "admission"
            report = decider.build_outputs(output_dir)
            self.assertEqual(report["batch2_relation_admission_count"], 9)
            self.assertTrue((output_dir / "artifact_manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
