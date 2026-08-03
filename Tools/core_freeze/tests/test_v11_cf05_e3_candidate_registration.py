import json
import re
import unittest

from Tools.core_freeze.e3_routing import build_e3_candidate_registration as builder


OUTPUT_DIR = builder.WORKSPACE / "outputs" / "v11_cf05_e3_registration_candidates_batch1_v1_20260803"


def load_output(filename: str):
    return json.loads((OUTPUT_DIR / filename).read_text(encoding="utf-8"))


class V11Cf05E3CandidateRegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = builder.load_json(builder.CONFIG_PATH)
        cls.registry = load_output("candidate_registration_registry.json")
        cls.runtime = load_output("candidate_runtime_contract_results.json")
        cls.similarity = load_output("candidate_relation_similarity.json")
        cls.report = load_output("candidate_registration_report.json")

    def test_all_input_bindings_are_hash_locked(self):
        for binding in self.config["bindings"]:
            path = builder.WORKSPACE / binding["path"]
            self.assertEqual(builder.sha256_file(path), binding["sha256"])

    def test_stable_candidate_ids_are_unique_and_do_not_collide_with_catalog(self):
        ids = [row["candidate_tool_id"] for row in self.registry["candidates"]]
        self.assertEqual(ids, ["E3C001", "E3C002", "E3C003", "E3C004", "E3C005"])
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(re.fullmatch(r"E3C\d{3}", value) for value in ids))
        catalog_binding = next(
            row for row in self.config["bindings"]
            if row["path"].endswith("e3_schema_catalog_v1_candidate.json")
        )
        catalog = builder.load_json(builder.WORKSPACE / catalog_binding["path"])
        formal_ids = {row["tool_id"] for row in catalog["entries"]}
        self.assertFalse(set(ids) & formal_ids)

    def test_all_five_candidates_have_complete_nonformal_function_schemas(self):
        self.assertEqual(self.registry["candidate_count"], 5)
        for row in self.registry["candidates"]:
            function = row["openai_tool"]["function"]
            parameters = function["parameters"]
            self.assertEqual(function["name"], row["candidate_tool_id"])
            self.assertEqual(parameters["type"], "object")
            self.assertTrue(parameters["properties"])
            self.assertTrue(parameters["required"])
            self.assertFalse(parameters["additionalProperties"])
            self.assertTrue(row["runtime_contract_passed"])
            self.assertEqual(row["lifecycle_status"], "candidate_registered_nonformal")
            self.assertFalse(row["formal_catalog_entry"])
            self.assertFalse(row["formal_execution_allowed"])
            self.assertFalse(row["formal_pool_inclusion_allowed"])

    def test_all_runtime_success_and_failure_contracts_pass(self):
        self.assertEqual(self.runtime["case_count"], 10)
        self.assertTrue(all(row["contract_outcome_pass"] for row in self.runtime["rows"]))
        self.assertEqual(self.report["runtime_smoke_pass_count"], 10)
        self.assertTrue(self.report["all_runtime_contracts_passed"])

    def test_relation_candidates_split_into_frozen_tracks(self):
        relation_by_id = {
            row["candidate_tool_id"]: row["registration_candidate_relation"]
            for row in self.similarity["rows"]
        }
        self.assertEqual(
            relation_by_id,
            {
                "E3C001": "acceptable_equivalent",
                "E3C002": "contract_mismatch",
                "E3C003": "lexical",
                "E3C004": "contract_mismatch",
                "E3C005": "contract_mismatch",
            },
        )
        self.assertEqual(
            self.report["relation_candidate_counts"],
            {
                "acceptable_equivalent": 1,
                "lexical": 1,
                "contract_mismatch": 3,
                "evidence_insufficient": 0,
            },
        )

    def test_equivalence_evidence_overrides_mismatch_similarity_for_pint(self):
        pint = next(row for row in self.similarity["rows"] if row["candidate_tool_id"] == "E3C001")
        self.assertTrue(pint["provable_contract_mismatch_neighbor"])
        self.assertTrue(pint["relation_evidence_passed"])
        self.assertEqual(pint["registration_candidate_relation"], "acceptable_equivalent")
        self.assertFalse(pint["formal_relation_admission"])

    def test_formal_catalog_and_pool_are_unchanged(self):
        self.assertEqual(self.report["formal_catalog_size_before"], 120)
        self.assertEqual(self.report["formal_catalog_size_after"], 120)
        self.assertEqual(self.report["formal_catalog_increment_count"], 0)
        self.assertEqual(self.report["formal_acceptable_tools_admission_count"], 0)
        self.assertEqual(self.report["formal_neighbor_admission_count"], 0)
        self.assertEqual(self.report["filled_relation_slot_count"], 0)
        self.assertEqual(self.report["remaining_lexical_gap"], 30)
        self.assertEqual(self.report["remaining_contract_mismatch_gap"], 40)
        self.assertEqual(self.report["external_api_calls"], 0)
        self.assertFalse(self.report["formal_pool_generation_allowed"])
        self.assertFalse(self.report["confirmatory_inference_allowed"])
        self.assertFalse(self.report["core_frozen"])

    def test_manifest_covers_every_registration_artifact(self):
        manifest = load_output("artifact_manifest.json")
        self.assertEqual(manifest["artifact_count"], 6)
        for artifact in manifest["artifacts"]:
            path = OUTPUT_DIR / artifact["filename"]
            self.assertEqual(builder.sha256_file(path), artifact["sha256"])
            self.assertEqual(path.stat().st_size, artifact["bytes"])


if __name__ == "__main__":
    unittest.main()
