import hashlib
import json
import unittest

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common
from Tools.core_freeze.e3_routing import build_a002_a003_minimal_pair_taskset as taskset


class V11Cf05E3A002A003MinimalPairTasksetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = taskset.build(common.load_json(taskset.CONFIG_PATH))

    def test_adopted_governance_authorizes_taskset(self):
        adoption = self.result["adoption"]
        self.assertEqual(adoption["decision"], "adopted")
        self.assertEqual(adoption["adopted_rules"]["family_id"], "CHEMICAL_FORMULA_ANALYSIS-V1")
        self.assertFalse(adoption["adopted_rules"]["h3_symmetric_neighbor_eligibility"])

    def test_taskset_has_eight_balanced_pairs(self):
        report = self.result["report"]
        self.assertEqual(report["pair_count"], 8)
        self.assertEqual(report["task_count"], 16)
        self.assertEqual(report["element_task_count"], 8)
        self.assertEqual(report["molar_mass_task_count"], 8)

    def test_each_pair_changes_only_requested_output_clause(self):
        tasks = self.result["tasks"]
        for index in range(0, len(tasks), 2):
            with self.subTest(pair_id=tasks[index]["pair_id"]):
                left, right = tasks[index], tasks[index + 1]
                self.assertEqual(left["pair_id"], right["pair_id"])
                self.assertEqual(left["canonical_inputs"], right["canonical_inputs"])
                self.assertEqual(
                    left["problem_text"].split("任务：", 1)[0],
                    right["problem_text"].split("任务：", 1)[0],
                )
                self.assertNotEqual(left["pair_variant"], right["pair_variant"])

    def test_independent_reference_values_are_frozen(self):
        by_formula = {row["formula"]: row for row in self.result["references"]}
        expected = {
            "Fe2O3": 159.687,
            "H2SO4": 98.072,
            "CaCO3": 100.086,
            "CuSO4": 159.602,
            "(NH4)2SO4": 132.134,
            "Ca(OH)2": 74.092,
            "[Cu(NH3)4]SO4": 227.726,
            "FeS": 87.905,
        }
        self.assertEqual(set(by_formula), set(expected))
        for formula, value in expected.items():
            with self.subTest(formula=formula):
                self.assertEqual(by_formula[formula]["molar_mass"], value)
                self.assertTrue(by_formula[formula]["oracle_independent_of_tool_runtime"])

    def test_all_local_runtime_checks_pass_after_reference_construction(self):
        report = self.result["report"]
        self.assertEqual(report["runtime_validation_passed_count"], 8)
        self.assertEqual(report["local_tool_calls_executed"], 16)
        self.assertTrue(all(row["passed"] for row in self.result["validation_rows"]))

    def test_asymmetric_selection_labels_are_encoded(self):
        parse_task = next(row for row in self.result["tasks"] if row["pair_variant"] == "element_stoichiometry")
        mass_task = next(row for row in self.result["tasks"] if row["pair_variant"] == "molar_mass")
        self.assertFalse(parse_task["expected_family_metrics"]["A003"]["scientific"])
        self.assertTrue(mass_task["expected_family_metrics"]["A002"]["alternative"])
        self.assertTrue(mass_task["expected_family_metrics"]["A002"]["scientific"])

    def test_full_catalog_gold_is_not_overclaimed(self):
        report = self.result["report"]
        self.assertFalse(report["full_catalog_acceptable_set_frozen"])
        self.assertTrue(report["requires_pool_specific_acceptable_tool_revalidation"])
        for row in self.result["tasks"]:
            self.assertFalse(row["full_catalog_acceptable_set_frozen"])
            self.assertTrue(row["requires_pool_specific_acceptable_tool_revalidation"])

    def test_no_external_or_confirmatory_use_occurred(self):
        report = self.result["report"]
        self.assertEqual(report["external_api_calls"], 0)
        self.assertFalse(report["formal_gold_mutated"])
        self.assertFalse(report["confirmatory_use_allowed"])

    def test_manifest_matches_outputs(self):
        output_dir = common.WORKSPACE / "outputs/v11_cf05_e3_a002_a003_minimal_pair_taskset_v1_20260811"
        manifest = json.loads((output_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["artifact_count"], 6)
        for row in manifest["artifacts"]:
            path = output_dir / row["filename"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])


if __name__ == "__main__":
    unittest.main()
