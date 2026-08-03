import copy
import json
import unittest

from Tools.core_freeze.e3_routing import pint_unit_adapter
from Tools.core_freeze.e3_routing import run_e3_candidate_holdout as runner


OUTPUT_DIR = runner.WORKSPACE / "outputs" / "v11_cf05_e3_candidate_holdout_batch1_r1_20260803"


def load_output(filename: str):
    return json.loads((OUTPUT_DIR / filename).read_text(encoding="utf-8"))


class V11Cf05E3CandidateHoldoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = runner.load_json(runner.CONFIG_PATH)
        cls.report = load_output("candidate_holdout_run_report.json")
        cls.acceptable = load_output("acceptable_equivalence_holdout_results.json")
        cls.mismatches = load_output("contract_mismatch_holdout_results.json")
        cls.novelty = load_output("holdout_input_novelty_report.json")

    def test_pint_contract_is_frozen_to_a001_scope(self):
        contract_path = runner.WORKSPACE / self.config["pint_contract_path"]
        self.assertEqual(runner.sha256_file(contract_path), self.config["pint_contract_sha256"])
        contract = runner.load_json(contract_path)
        self.assertEqual(contract["provisional_candidate_id"], "SRC-PINT-001")
        self.assertEqual(contract["target_tool_id"], "A001")
        self.assertEqual(len(contract["frozen_scope"]["unit_pairs"]), 8)
        self.assertFalse(contract["input_contract"]["additionalProperties"])
        self.assertFalse(contract["acceptable_relation"]["scientific_function_distinct"])
        self.assertFalse(contract["acceptable_relation"]["catalog_increment_allowed"])
        self.assertFalse(contract["formal_registration_allowed"])

    def test_adapter_rejects_invalid_input_before_loading_pint(self):
        invalid_value = pint_unit_adapter.invoke(
            {"value": float("inf"), "source_unit": "kg", "target_unit": "g"}
        )
        self.assertFalse(invalid_value["success"])
        self.assertEqual(invalid_value["error_code"], "INVALID_INPUT")
        unsupported = pint_unit_adapter.invoke(
            {"value": 1, "source_unit": "g", "target_unit": "kg"}
        )
        self.assertFalse(unsupported["success"])
        self.assertEqual(unsupported["error_code"], "UNSUPPORTED_PAIR")

    def test_holdout_inputs_do_not_copy_frozen_reference_content(self):
        self.assertTrue(self.novelty["input_novelty_passed"])
        self.assertEqual(self.novelty["frozen_reference_case_count"], 27)
        self.assertEqual(self.novelty["proposed_case_count"], 11)
        self.assertEqual(self.novelty["exact_input_duplicates_with_frozen_references"], [])
        self.assertEqual(self.novelty["duplicate_inputs_within_holdout"], [])

    def test_all_seven_pint_holdout_cases_match_a001(self):
        self.assertEqual(self.acceptable["case_count"], 7)
        self.assertTrue(all(row["comparison_pass"] for row in self.acceptable["rows"]))
        self.assertTrue(self.report["pint_runtime_verification_passed"])
        self.assertTrue(self.report["pint_registration_candidate_ready"])

    def test_all_four_contract_mismatch_mechanisms_replicate(self):
        self.assertEqual(self.mismatches["case_count"], 4)
        self.assertEqual(
            {row["candidate_id"] for row in self.mismatches["rows"]},
            {"SRC-PMG-001", "SRC-RDKIT-004", "SRC-PMG-002", "SRC-PMG-003"},
        )
        self.assertTrue(all(row["relation_fixture_pass"] for row in self.mismatches["rows"]))
        self.assertTrue(self.report["relation_fixture_verification_passed"])
        self.assertEqual(self.report["contract_mismatch_fixture_pass_count"], 4)

    def test_exact_reference_duplicate_is_rejected_by_novelty_check(self):
        reference_path = next(
            runner.WORKSPACE / row["path"]
            for row in self.config["bindings"]
            if row["path"].endswith("reference_cases_v1.json")
        )
        invalid = copy.deepcopy(self.config)
        invalid["acceptable_equivalence_cases"][0]["input"] = {
            "value": 1,
            "source_unit": "kg",
            "target_unit": "g",
        }
        result = runner.verify_novel_inputs(invalid, runner.load_json(reference_path))
        self.assertFalse(result["input_novelty_passed"])
        self.assertEqual(len(result["exact_input_duplicates_with_frozen_references"]), 1)

    def test_formal_counts_remain_unchanged(self):
        self.assertEqual(self.report["formal_acceptable_tools_admission_count"], 0)
        self.assertEqual(self.report["formal_neighbor_admission_count"], 0)
        self.assertEqual(self.report["catalog_increment_count"], 0)
        self.assertEqual(self.report["filled_relation_slot_count"], 0)
        self.assertEqual(self.report["remaining_lexical_gap"], 30)
        self.assertEqual(self.report["remaining_contract_mismatch_gap"], 40)
        self.assertEqual(self.report["external_api_calls"], 0)
        self.assertFalse(self.report["formal_pool_generation_allowed"])
        self.assertFalse(self.report["confirmatory_inference_allowed"])
        self.assertFalse(self.report["core_frozen"])

    def test_manifest_covers_all_run_artifacts(self):
        manifest = load_output("artifact_manifest.json")
        self.assertEqual(manifest["artifact_count"], 7)
        for artifact in manifest["artifacts"]:
            path = OUTPUT_DIR / artifact["filename"]
            self.assertEqual(runner.sha256_file(path), artifact["sha256"])
            self.assertEqual(path.stat().st_size, artifact["bytes"])


if __name__ == "__main__":
    unittest.main()
