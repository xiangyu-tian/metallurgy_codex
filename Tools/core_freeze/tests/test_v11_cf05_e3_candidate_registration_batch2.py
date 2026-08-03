import copy
import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.e3_routing import build_e3_candidate_registration_batch2 as builder
from Tools.core_freeze.e3_routing import candidate_runtime_adapters


OUTPUT_DIR = builder.WORKSPACE / "outputs" / "v11_cf05_e3_registration_candidates_batch2_v1_20260803"


def load_output(filename: str):
    return json.loads((OUTPUT_DIR / filename).read_text(encoding="utf-8"))


class V11Cf05E3CandidateRegistrationBatch2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = builder.load_json(builder.CONFIG_PATH)
        cls.registry = load_output("candidate_registration_registry.json")
        cls.runtime = load_output("candidate_runtime_contract_results.json")
        cls.relations = load_output("candidate_relation_evidence.json")
        cls.blocked = load_output("blocked_candidate_registry.json")
        cls.report = load_output("candidate_registration_report.json")

    def test_bindings_and_environment_are_frozen(self):
        for row in self.config["bindings"]:
            path = builder.WORKSPACE / row["path"]
            self.assertEqual(builder.sha256_file(path), row["sha256"])
        self.assertTrue(self.report["environment_verification_passed"])

    def test_twelve_ids_are_reserved_but_only_ten_have_adapters(self):
        registered = [row["candidate_tool_id"] for row in self.registry["candidates"]]
        blocked = [row["candidate_tool_id"] for row in self.blocked["candidates"]]
        self.assertEqual(registered, [f"E3C{number:03d}" for number in range(6, 16)])
        self.assertEqual(blocked, ["E3C016", "E3C017"])
        self.assertEqual(set(registered), set(candidate_runtime_adapters.BATCH2_ADAPTERS))
        self.assertEqual(self.report["candidate_id_reservation_count"], 12)
        self.assertEqual(self.report["implemented_candidate_count"], 10)
        self.assertEqual(self.report["blocked_candidate_count"], 2)

    def test_all_normal_boundary_and_failure_contracts_pass(self):
        self.assertEqual(self.runtime["case_count"], 30)
        self.assertEqual(
            {row["case_kind"] for row in self.runtime["rows"]},
            {"normal", "boundary", "failure"},
        )
        counts = {
            kind: sum(row["case_kind"] == kind for row in self.runtime["rows"])
            for kind in ("normal", "boundary", "failure")
        }
        self.assertEqual(counts, {"normal": 10, "boundary": 10, "failure": 10})
        self.assertTrue(all(row["contract_outcome_pass"] for row in self.runtime["rows"]))
        self.assertEqual(self.report["runtime_pass_count"], 30)

    def test_relations_are_disjoint_and_only_threshold_passes_are_admissible(self):
        rows = self.relations["rows"]
        self.assertEqual(len(rows), 10)
        self.assertEqual(len({row["candidate_tool_id"] for row in rows}), 10)
        for row in rows:
            if row["candidate_tool_id"] == "E3C007":
                self.assertFalse(row["relation_evidence_passed"])
                self.assertEqual(row["registration_candidate_relation"], "evidence_insufficient")
                self.assertFalse(row["algorithmic_lexical_candidate"])
                continue
            self.assertTrue(row["relation_evidence_passed"])
            if row["registration_candidate_relation"] == "lexical":
                self.assertTrue(row["algorithmic_lexical_candidate"])
            else:
                self.assertEqual(row["registration_candidate_relation"], "contract_mismatch")
                self.assertTrue(row["provable_contract_mismatch_neighbor"])
        self.assertEqual(
            self.report["relation_candidate_counts"],
            {"contract_mismatch": 4, "evidence_insufficient": 1, "lexical": 5},
        )

    def test_pycalphad_is_blocked_by_missing_scientific_asset_not_package(self):
        for row in self.blocked["candidates"]:
            self.assertEqual(row["blocker_code"], "THERMODYNAMIC_DATABASE_NOT_FROZEN")
            self.assertIn("TDB", row["blocker"])
            self.assertTrue(row["unblock_requirement"])
            execution = candidate_runtime_adapters.invoke_batch2(row["candidate_tool_id"], {})
            self.assertFalse(execution["success"])
            self.assertEqual(execution["error_code"], "UNKNOWN_OR_BLOCKED_CANDIDATE_TOOL")

    def test_formal_catalog_and_pool_remain_unchanged(self):
        self.assertEqual(self.report["formal_catalog_size"], 120)
        self.assertEqual(self.report["formal_catalog_increment_count"], 0)
        self.assertEqual(self.report["formal_relation_admission_count"], 0)
        self.assertEqual(self.report["external_api_calls"], 0)
        self.assertFalse(self.report["formal_pool_generation_allowed"])
        self.assertFalse(self.report["confirmatory_inference_allowed"])
        self.assertFalse(self.report["core_frozen"])

    def test_policy_mutation_is_rejected(self):
        invalid = copy.deepcopy(self.config)
        invalid["formal_pool_generation_allowed"] = True
        with self.assertRaisesRegex(ValueError, "must remain false"):
            builder.build_package(invalid)

    def test_manifest_covers_every_artifact(self):
        manifest = load_output("artifact_manifest.json")
        self.assertEqual(manifest["artifact_count"], 7)
        for row in manifest["artifacts"]:
            path = OUTPUT_DIR / row["filename"]
            self.assertEqual(builder.sha256_file(path), row["sha256"])
            self.assertEqual(path.stat().st_size, row["bytes"])

    def test_fresh_output_reproduces_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "batch2"
            report = builder.build_outputs(output_dir)
            self.assertEqual(report["runtime_pass_count"], 30)
            self.assertTrue((output_dir / "artifact_manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
