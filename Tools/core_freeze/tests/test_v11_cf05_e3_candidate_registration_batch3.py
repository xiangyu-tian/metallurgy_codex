import copy
import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.e3_routing import build_e3_candidate_registration_batch3 as builder
from Tools.core_freeze.e3_routing import candidate_runtime_adapters


OUTPUT_DIR = builder.WORKSPACE / "outputs" / "v11_cf05_e3_registration_candidates_batch3_v1_20260803"


def load_output(filename: str):
    return json.loads((OUTPUT_DIR / filename).read_text(encoding="utf-8"))


class V11Cf05E3CandidateRegistrationBatch3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = builder.load_json(builder.CONFIG_PATH)
        cls.registry = load_output("candidate_registration_registry.json")
        cls.runtime = load_output("candidate_runtime_contract_results.json")
        cls.relations = load_output("candidate_relation_evidence.json")
        cls.independence = load_output("candidate_independence_matrix.json")
        cls.report = load_output("candidate_registration_report.json")

    def test_bindings_and_environment_are_frozen(self):
        for row in self.config["bindings"]:
            path = builder.WORKSPACE / row["path"]
            self.assertEqual(builder.sha256_file(path), row["sha256"])
        self.assertTrue(self.report["environment_verification_passed"])

    def test_exactly_eight_a003_callable_contracts_are_registered(self):
        candidates = self.registry["candidates"]
        self.assertEqual([row["candidate_tool_id"] for row in candidates], [f"E3C{number:03d}" for number in range(18, 26)])
        self.assertEqual({row["target_tool_id"] for row in candidates}, {"A003"})
        self.assertEqual({row["candidate_tool_id"] for row in candidates}, set(candidate_runtime_adapters.BATCH3_ADAPTERS))
        self.assertEqual(len({row["semantic_alias"] for row in candidates}), 8)
        self.assertEqual(len({row["callable_identity"] for row in candidates}), 8)

    def test_normal_boundary_and_failure_contracts_all_pass(self):
        self.assertEqual(self.runtime["case_count"], 24)
        counts = {
            kind: sum(row["case_kind"] == kind for row in self.runtime["rows"])
            for kind in ("normal", "boundary", "failure")
        }
        self.assertEqual(counts, {"normal": 8, "boundary": 8, "failure": 8})
        self.assertTrue(all(row["contract_outcome_pass"] for row in self.runtime["rows"]))
        self.assertEqual(self.report["runtime_pass_count"], 24)

    def test_frozen_relation_dose_is_two_lexical_and_six_mismatch(self):
        rows = self.relations["rows"]
        self.assertEqual(len(rows), 8)
        self.assertTrue(all(row["relation_evidence_passed"] for row in rows))
        counts = {
            relation: sum(row["registration_candidate_relation"] == relation for row in rows)
            for relation in ("lexical", "contract_mismatch")
        }
        self.assertEqual(counts, {"lexical": 2, "contract_mismatch": 6})
        for row in rows:
            if row["registration_candidate_relation"] == "lexical":
                self.assertTrue(row["algorithmic_lexical_candidate"])
            else:
                self.assertTrue(row["provable_contract_mismatch_neighbor"])

    def test_a003_reaches_paired_eight_only_if_admitted(self):
        self.assertEqual(self.report["a003_lexical_count_if_admitted"], 8)
        self.assertEqual(self.report["a003_contract_mismatch_count_if_admitted"], 8)
        self.assertTrue(self.report["a003_paired_8_ready_if_admitted"])
        self.assertEqual(self.report["lexical_gap_if_admitted"], 22)
        self.assertEqual(self.report["contract_mismatch_gap_if_admitted"], 27)

    def test_independence_matrix_forbids_same_callable_renaming(self):
        rows = self.independence["rows"]
        self.assertEqual(len(rows), 8)
        self.assertEqual(len({row["callable_identity"] for row in rows}), 8)
        self.assertTrue(all(not row["same_callable_renaming"] for row in rows))
        self.assertTrue(all(row["distinct_input_or_output_contract"] for row in rows))
        self.assertTrue(all(row["source_reference"].startswith("https://") for row in rows))

    def test_formal_catalog_and_pool_are_not_mutated(self):
        self.assertEqual(self.report["formal_catalog_size"], 120)
        self.assertEqual(self.report["formal_catalog_increment_count"], 0)
        self.assertEqual(self.report["formal_relation_admission_count"], 0)
        self.assertEqual(self.report["external_api_calls"], 0)
        self.assertFalse(self.report["formal_pool_generation_allowed"])
        self.assertFalse(self.report["confirmatory_inference_allowed"])
        self.assertFalse(self.report["core_frozen"])

    def test_policy_or_dose_mutation_is_rejected(self):
        invalid_policy = copy.deepcopy(self.config)
        invalid_policy["formal_pool_generation_allowed"] = True
        with self.assertRaisesRegex(ValueError, "must remain false"):
            builder.build_package(invalid_policy)

        invalid_dose = copy.deepcopy(self.config)
        invalid_dose["implemented_candidates"][0]["relation_policy"] = "contract_mismatch"
        with self.assertRaisesRegex(ValueError, "exactly two lexical and six mismatch"):
            builder.build_package(invalid_dose)

    def test_manifest_covers_every_artifact(self):
        manifest = load_output("artifact_manifest.json")
        self.assertEqual(manifest["artifact_count"], 7)
        for row in manifest["artifacts"]:
            path = OUTPUT_DIR / row["filename"]
            self.assertEqual(builder.sha256_file(path), row["sha256"])
            self.assertEqual(path.stat().st_size, row["bytes"])

    def test_fresh_output_reproduces_semantic_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "batch3"
            report = builder.build_outputs(output_dir)
            self.assertEqual(report, self.report)
            self.assertTrue((output_dir / "artifact_manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
