import copy
import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.e3_routing import build_e3_candidate_contract_package as builder


class V11Cf05E3CandidateContractPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = builder.load_json(builder.CONFIG_PATH)
        cls.result = builder.build_package(cls.config)

    def test_contracts_cover_exactly_the_twelve_draft_queue_entries(self):
        drafts = self.result["contract_drafts"]
        self.assertEqual(drafts["contract_count"], 12)
        self.assertEqual(
            self.result["summary"]["contract_draft_count_by_target"],
            {"A001": 1, "A002": 3, "A003": 2, "A004": 4, "B019": 2},
        )
        self.assertTrue(
            all(row["draft_status"] == "structurally_complete_execution_unverified" for row in drafts["contracts"])
        )

    def test_every_contract_has_callable_structure_but_no_runtime_identity(self):
        for row in self.result["contract_drafts"]["contracts"]:
            self.assertTrue(row["input_contract"]["parameters"])
            self.assertTrue(row["input_contract"]["required"])
            self.assertTrue(row["output_contract"]["properties"])
            self.assertIn("units", row["output_contract"])
            self.assertTrue(row["applicability_contract"]["systems"])
            self.assertTrue(row["applicability_contract"]["exclusions"])
            self.assertFalse(row["dependency_import_available"])
            self.assertFalse(row["execution_allowed"])
            self.assertFalse(row["admission_allowed"])
            self.assertIsNone(row["independence_evidence_passed"])
            self.assertIsNone(row["relation_fixture_passed"])

    def test_equivalence_plan_uses_frozen_reference_cases_without_results(self):
        plan = self.result["equivalence_plan"]
        self.assertEqual(plan["test_plan_count"], 5)
        self.assertEqual(self.result["summary"]["equivalence_reference_case_count"], 21)
        for row in plan["tests"]:
            self.assertTrue(row["overlap_reference_case_ids"])
            self.assertTrue(row["boundary_reference_case_ids"])
            self.assertEqual(row["execution_status"], "not_started_dependency_unavailable")
            self.assertIsNone(row["observed_case_results"])
            self.assertIsNone(row["equivalence_classification"])
            self.assertFalse(row["may_enter_acceptable_tool_set"])
            self.assertFalse(row["may_enter_unacceptable_neighbor_set"])

    def test_operational_equivalence_requires_general_input_adapter(self):
        plans = {
            row["provisional_candidate_id"]: row
            for row in self.result["equivalence_plan"]["tests"]
        }
        self.assertFalse(plans["SRC-RDKIT-004"]["adapter_generalizable_over_target_scope"])
        self.assertFalse(plans["SRC-PMG-003"]["adapter_generalizable_over_target_scope"])
        self.assertTrue(plans["SRC-PMG-001"]["adapter_generalizable_over_target_scope"])

    def test_similarity_thresholds_are_not_final_relation_decisions(self):
        summary = self.result["summary"]
        self.assertEqual(summary["name_threshold_pass_count"], 9)
        self.assertEqual(summary["structured_contract_threshold_pass_count"], 12)
        self.assertEqual(summary["final_lexical_relation_pass_count"], 0)
        self.assertEqual(summary["final_contract_mismatch_relation_pass_count"], 0)
        for row in self.result["similarity"]["rows"]:
            self.assertFalse(row["final_lexical_relation_pass"])
            self.assertFalse(row["final_contract_mismatch_relation_pass"])

    def test_b019_drafts_explicitly_exclude_direct_lever_rule_use(self):
        rows = [
            row
            for row in self.result["contract_drafts"]["contracts"]
            if row["target_tool_id"] == "B019"
        ]
        self.assertEqual(len(rows), 2)
        self.assertTrue(
            all(
                any("lever-rule" in text for text in row["applicability_contract"]["exclusions"])
                for row in rows
            )
        )

    def test_design_does_not_change_catalog_or_gap_counts(self):
        summary = self.result["summary"]
        self.assertEqual(summary["dependency_installations"], 0)
        self.assertEqual(summary["external_api_calls"], 0)
        self.assertEqual(summary["admission_ready_contract_count"], 0)
        self.assertEqual(summary["catalog_increment_count"], 0)
        self.assertEqual(summary["filled_relation_slot_count"], 0)
        self.assertEqual(summary["remaining_lexical_gap"], 30)
        self.assertEqual(summary["remaining_contract_mismatch_gap"], 40)
        self.assertFalse(summary["formal_pool_generation_allowed"])

    def test_missing_contract_draft_is_rejected(self):
        invalid = copy.deepcopy(self.config)
        invalid["contracts"].pop()
        with self.assertRaisesRegex(ValueError, "cover the contract_draft_queue exactly"):
            builder.build_package(invalid)

    def test_output_manifest_is_complete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            builder.build_outputs(output_dir)
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["artifact_count"], 7)
            for artifact in manifest["artifacts"]:
                path = output_dir / artifact["filename"]
                self.assertTrue(path.is_file())
                self.assertEqual(builder.sha256_file(path), artifact["sha256"])


if __name__ == "__main__":
    unittest.main()
