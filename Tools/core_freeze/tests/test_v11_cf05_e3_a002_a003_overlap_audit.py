import hashlib
import json
import unittest

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common
from Tools.core_freeze.e3_routing import audit_a002_a003_overlap as overlap


class V11Cf05E3A002A003OverlapAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = overlap.audit(common.load_json(overlap.CONFIG_PATH))

    def test_all_frozen_a003_tasks_are_audited(self):
        report = self.result["report"]
        self.assertEqual(report["task_count"], 12)
        self.assertEqual(report["local_tool_calls_executed"], 24)

    def test_a002_and_a003_molar_mass_values_match(self):
        report = self.result["report"]
        self.assertEqual(report["a002_numeric_pass_count"], 12)
        self.assertEqual(report["a002_a003_numeric_equal_count"], 12)
        self.assertTrue(all(row["a002_a003_numeric_equal"] for row in self.result["rows"]))

    def test_primary_and_alternative_policies_remain_separate(self):
        report = self.result["report"]
        self.assertEqual(report["a002_explicit_unit_count"], 0)
        self.assertEqual(report["a002_primary_direct_acceptable_count"], 0)
        self.assertEqual(report["a002_alternative_success_count"], 12)
        self.assertFalse(report["primary_acceptable_sets_changed"])
        self.assertTrue(report["alternative_success_sets_expanded"])

    def test_rc2_candidate_preserves_primary_sets_and_adds_a002_as_alternative(self):
        for task in self.result["revised_tasks"]:
            with self.subTest(task_id=task["task_id"]):
                self.assertEqual(
                    task["primary_acceptable_tools_rc2_candidate"],
                    task["revalidated_primary_acceptable_tools"],
                )
                self.assertIn("A002", task["alternative_success_tools_rc2_candidate"])
                self.assertFalse(task["formal_gold_mutated"])

    def test_relation_is_asymmetric_not_independent(self):
        relation = self.result["relation"]
        self.assertEqual(relation["relation_type"], "asymmetric_output_overlap")
        self.assertEqual(
            relation["independent_tool_count_recommendation"],
            "do_not_count_as_independent_until_family_governance_review",
        )

    def test_contracts_share_formula_and_molar_mass(self):
        a002 = self.result["contracts"]["A002"]
        a003 = self.result["contracts"]["A003"]
        self.assertEqual(a002["required_inputs"], ["formula"])
        self.assertEqual(a003["required_inputs"], ["formula"])
        self.assertIn("molar_mass", a002["output_contract"])
        self.assertIn("molar_mass", a003["output_contract"])

    def test_no_external_or_formal_mutation_occurred(self):
        report = self.result["report"]
        self.assertEqual(report["external_api_calls"], 0)
        self.assertFalse(report["runtime_mutation_performed"])
        self.assertFalse(report["formal_catalog_mutated"])
        self.assertFalse(report["formal_gold_mutated"])

    def test_manifest_matches_outputs(self):
        output_dir = common.WORKSPACE / "outputs/v11_cf05_e3_a002_a003_overlap_audit_v1_20260811"
        manifest = json.loads((output_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["artifact_count"], 7)
        for row in manifest["artifacts"]:
            path = output_dir / row["filename"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])


if __name__ == "__main__":
    unittest.main()
