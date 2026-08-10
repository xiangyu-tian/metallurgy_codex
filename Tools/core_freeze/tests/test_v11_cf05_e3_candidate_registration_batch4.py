import copy
import json
import shutil
import unittest
import uuid
from collections import Counter

from Tools.core_freeze.e3_routing import build_e3_candidate_registration_batch4 as builder
from Tools.core_freeze.e3_routing import candidate_runtime_adapters


OUTPUT_DIR = builder.WORKSPACE / "outputs" / "v11_cf05_e3_registration_candidates_batch4_v1_20260810"


def load_output(filename):
    return json.loads((OUTPUT_DIR / filename).read_text(encoding="utf-8"))


class V11Cf05E3CandidateRegistrationBatch4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = builder.load_json(builder.CONFIG_PATH)
        cls.registry = load_output("candidate_registration_registry.json")
        cls.runtime = load_output("candidate_runtime_contract_results.json")
        cls.relations = load_output("candidate_relation_evidence.json")
        cls.report = load_output("candidate_registration_report.json")

    def test_two_independent_a004_candidates_are_registered(self):
        candidates = self.registry["candidates"]
        self.assertEqual([row["candidate_tool_id"] for row in candidates], ["E3C026", "E3C027"])
        self.assertEqual({row["target_tool_id"] for row in candidates}, {"A004"})
        self.assertEqual(set(candidate_runtime_adapters.BATCH4_ADAPTERS), {"E3C026", "E3C027"})
        self.assertEqual(len({row["callable_identity"] for row in candidates}), 2)

    def test_normal_boundary_failure_contracts_pass(self):
        self.assertEqual(self.runtime["case_count"], 6)
        self.assertEqual(
            Counter(row["case_kind"] for row in self.runtime["rows"]),
            Counter({"normal": 2, "boundary": 2, "failure": 2}),
        )
        self.assertTrue(all(row["contract_outcome_pass"] for row in self.runtime["rows"]))

    def test_relation_dose_is_one_lexical_and_one_mismatch(self):
        rows = self.relations["rows"]
        self.assertEqual(
            Counter(row["registration_candidate_relation"] for row in rows),
            Counter({"lexical": 1, "contract_mismatch": 1}),
        )
        self.assertTrue(all(row["relation_evidence_passed"] for row in rows))
        lexical = next(row for row in rows if row["registration_candidate_relation"] == "lexical")
        mismatch = next(row for row in rows if row["registration_candidate_relation"] == "contract_mismatch")
        self.assertTrue(lexical["algorithmic_lexical_candidate"])
        self.assertTrue(mismatch["provable_contract_mismatch_neighbor"])

    def test_a004_reaches_paired_four_only_if_admitted(self):
        self.assertEqual(self.report["a004_lexical_count_if_admitted"], 4)
        self.assertEqual(self.report["a004_contract_mismatch_count_if_admitted"], 4)
        self.assertTrue(self.report["a004_paired_4_ready_if_admitted"])
        self.assertFalse(self.report["a004_paired_8_ready_if_admitted"])

    def test_formal_state_remains_unchanged(self):
        self.assertEqual(self.report["formal_catalog_size"], 120)
        self.assertEqual(self.report["formal_catalog_increment_count"], 0)
        self.assertEqual(self.report["formal_relation_admission_count"], 0)
        self.assertEqual(self.report["external_api_calls"], 0)
        self.assertFalse(self.report["formal_pool_generation_allowed"])
        self.assertFalse(self.report["confirmatory_inference_allowed"])

    def test_policy_or_dose_mutation_is_rejected(self):
        invalid_policy = copy.deepcopy(self.config)
        invalid_policy["formal_pool_generation_allowed"] = True
        with self.assertRaisesRegex(ValueError, "must remain false"):
            builder.build_package(invalid_policy)
        invalid_dose = copy.deepcopy(self.config)
        invalid_dose["implemented_candidates"][0]["relation_policy"] = "contract_mismatch"
        with self.assertRaisesRegex(ValueError, "exactly one lexical and one mismatch"):
            builder.build_package(invalid_dose)

    def test_manifest_and_fresh_output_are_complete(self):
        manifest = load_output("artifact_manifest.json")
        self.assertEqual(manifest["artifact_count"], 7)
        for row in manifest["artifacts"]:
            path = OUTPUT_DIR / row["filename"]
            self.assertEqual(builder.sha256_file(path), row["sha256"])
        output_dir = builder.WORKSPACE / "outputs" / f".batch4-registration-test-{uuid.uuid4().hex}"
        try:
            self.assertEqual(builder.build_outputs(output_dir), self.report)
        finally:
            if output_dir.exists():
                shutil.rmtree(output_dir)


if __name__ == "__main__":
    unittest.main()
