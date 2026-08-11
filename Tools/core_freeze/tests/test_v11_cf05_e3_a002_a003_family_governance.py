import hashlib
import json
import unittest

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common
from Tools.core_freeze.e3_routing import build_a002_a003_family_governance as governance


class V11Cf05E3A002A003FamilyGovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = governance.build(common.load_json(governance.CONFIG_PATH))

    def decision(self, case_id):
        return next(row for row in self.result["decision_table"] if row["case_id"] == case_id)

    def test_endpoint_and_capability_counts_are_separate(self):
        policy = self.result["policy"]
        self.assertEqual(policy["counting"]["callable_endpoint_count"], 2)
        self.assertEqual(policy["counting"]["family_deduplicated_capability_count"], 1)
        self.assertEqual(policy["counting"]["h4_primary_scale_axis"], "endpoint_schema_count")

    def test_a003_task_selecting_a002_is_alternative_scientific_success(self):
        row = self.decision("A003-TASK-SELECT-A002")
        self.assertFalse(row["primary_selection_correct"])
        self.assertTrue(row["tool_family_selection_correct"])
        self.assertTrue(row["alternative_success"])
        self.assertTrue(row["scientific_success_including_alternatives"])
        self.assertEqual(row["error_class"], "endpoint_preference_only")

    def test_a002_task_selecting_a003_is_not_scientific_success(self):
        row = self.decision("A002-TASK-SELECT-A003")
        self.assertFalse(row["primary_selection_correct"])
        self.assertTrue(row["tool_family_selection_correct"])
        self.assertFalse(row["alternative_success"])
        self.assertFalse(row["scientific_success_including_alternatives"])
        self.assertEqual(row["error_class"], "same_family_scientific_failure")

    def test_symmetric_h3_neighbor_use_is_prohibited(self):
        policy = self.result["policy"]
        self.assertFalse(policy["h3"]["eligible_as_symmetric_functional_neighbor_pair"])
        self.assertEqual(policy["h3"]["allowed_role"], "asymmetric_overlap_secondary_analysis")

    def test_primary_metric_cannot_be_overridden_by_secondary_metrics(self):
        metrics = self.result["policy"]["metrics"]
        self.assertEqual(metrics["primary"], "primary_acceptable_tool_selection_accuracy")
        self.assertFalse(metrics["primary_support_may_be_changed_by_secondary_metrics"])

    def test_existing_a003_results_remain_unchanged(self):
        report = self.result["report"]
        self.assertEqual(report["existing_a003_cell_count"], 96)
        self.assertEqual(report["existing_primary_success_count"], 96)
        self.assertEqual(report["existing_alternative_success_count"], 0)
        self.assertTrue(report["existing_primary_accuracy_unchanged"])

    def test_no_external_execution_or_formal_mutation_occurred(self):
        report = self.result["report"]
        self.assertEqual(report["external_api_calls"], 0)
        self.assertEqual(report["tool_calls_executed"], 0)
        self.assertFalse(report["formal_catalog_mutated"])
        self.assertFalse(report["formal_gold_mutated"])
        self.assertFalse(report["protocol_mutated"])

    def test_manifest_matches_outputs(self):
        output_dir = common.WORKSPACE / "outputs/v11_cf05_e3_a002_a003_family_governance_v1_20260811"
        manifest = json.loads((output_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["artifact_count"], 5)
        for row in manifest["artifacts"]:
            path = output_dir / row["filename"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])


if __name__ == "__main__":
    unittest.main()
