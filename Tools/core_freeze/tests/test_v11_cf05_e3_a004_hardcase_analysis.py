import copy
import unittest

from Tools.core_freeze.e3_routing import analyze_e3_a004_hardcase_development as analyzer


class V11Cf05E3A004HardcaseAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = analyzer.load_json(analyzer.CONFIG_PATH)
        cls.result = analyzer.build(cls.config)

    def test_result_grid_and_safety_contract(self):
        self.assertEqual(len(self.result["scored_rows"]), 48)
        report = self.result["overall_report"]
        self.assertTrue(report["all_transport_accepted"])
        self.assertEqual(report["tool_calls_executed"], 0)
        self.assertEqual(report["retries_executed"], 0)
        self.assertFalse(report["independent_validation_split_accessed"])

    def test_observed_failure_is_preserved(self):
        self.assertEqual(len(self.result["failure_rows"]), 1)
        failure = self.result["failure_rows"][0]
        self.assertEqual(failure["condition_id"], "contract_mismatch_4")
        self.assertEqual(failure["tool_pool_size"], 120)
        self.assertEqual(failure["method"], "dense_top5")
        self.assertEqual(failure["tool_call_count"], 3)

    def test_condition_summary_is_descriptive_only(self):
        by_condition = {row["condition_id"]: row for row in self.result["by_condition"]}
        self.assertEqual(by_condition["none_0"]["complete_call_accuracy"], 1.0)
        self.assertEqual(by_condition["lexical_4"]["complete_call_accuracy"], 1.0)
        self.assertEqual(by_condition["contract_mismatch_4"]["complete_call_accuracy"], 15 / 16)
        self.assertFalse(self.result["overall_report"]["confirmatory_inference_allowed"])

    def test_policy_escalation_is_rejected(self):
        invalid = copy.deepcopy(self.config)
        invalid["confirmatory_inference_allowed"] = True
        with self.assertRaisesRegex(ValueError, "policy changed"):
            analyzer.build(invalid)

    def test_committed_analysis_output_is_hash_complete(self):
        output_dir = analyzer.WORKSPACE / "outputs" / "v11_cf05_e3_a004_hardcase_r1_analysis_20260810"
        report = analyzer.load_json(output_dir / "a004_overall_report.json")
        self.assertEqual(report["overall"]["complete_call_accuracy"], 47 / 48)
        self.assertEqual(report["failure_count"], 1)
        manifest = analyzer.load_json(output_dir / "artifact_manifest.json")
        self.assertEqual(manifest["artifact_count"], 9)
        for row in manifest["artifacts"]:
            path = output_dir / row["filename"]
            self.assertTrue(path.is_file())
            self.assertEqual(analyzer.file_hash(path), row["sha256"])


if __name__ == "__main__":
    unittest.main()
