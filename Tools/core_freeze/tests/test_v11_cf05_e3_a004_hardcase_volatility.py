import copy
import unittest

from Tools.core_freeze.e3_routing import analyze_e3_a004_hardcase_volatility as analyzer


class V11Cf05E3A004HardcaseVolatilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = analyzer.load_json(analyzer.CONFIG_PATH)
        cls.result = analyzer.build(cls.config)

    def test_three_repeat_grid_is_complete(self):
        self.assertEqual(len(self.result["all_rows"]), 144)
        self.assertEqual(len(self.result["pair_rows"]), 48)
        self.assertEqual(len(self.result["repeat_scored"]), 96)

    def test_failure_is_stable_and_exactly_reproduced(self):
        summary = self.result["pairing_summary"]
        self.assertEqual(summary["stable_correct_count"], 47)
        self.assertEqual(summary["intermittent_count"], 0)
        self.assertEqual(summary["stable_failure_count"], 1)
        self.assertEqual(summary["exact_three_repeat_agreement_rate"], 1.0)
        recurrence = self.result["recurrence"]
        self.assertTrue(recurrence["r2_failure_recurred"])
        self.assertTrue(recurrence["r3_failure_recurred"])
        self.assertEqual(recurrence["tool_call_count_by_repeat"], [3, 3, 3])
        self.assertTrue(recurrence["exact_same_called_tool_sequence_all_repeats"])

    def test_each_repeat_has_same_accuracy(self):
        by_repeat = {row["model_run_repeat"]: row for row in self.result["by_repeat"]}
        for repeat in (1, 2, 3):
            self.assertEqual(by_repeat[repeat]["complete_call_accuracy"], 47 / 48)

    def test_analysis_remains_development_only(self):
        report = self.result["report"]
        self.assertFalse(report["significance_testing_performed"])
        self.assertFalse(report["confirmatory_inference_allowed"])
        invalid = copy.deepcopy(self.config)
        invalid["significance_testing_allowed"] = True
        with self.assertRaisesRegex(ValueError, "must remain false"):
            analyzer.build(invalid)

    def test_committed_volatility_output_is_hash_complete(self):
        output_dir = analyzer.WORKSPACE / "outputs" / "v11_cf05_e3_a004_hardcase_volatility_20260810"
        report = analyzer.load_json(output_dir / "a004_three_repeat_overall_report.json")
        self.assertEqual(report["pairing_summary"]["stable_failure_count"], 1)
        self.assertEqual(report["pairing_summary"]["exact_three_repeat_agreement_rate"], 1.0)
        manifest = analyzer.load_json(output_dir / "artifact_manifest.json")
        self.assertEqual(manifest["artifact_count"], 12)
        for row in manifest["artifacts"]:
            path = output_dir / row["filename"]
            self.assertTrue(path.is_file())
            self.assertEqual(analyzer.file_hash(path), row["sha256"])


if __name__ == "__main__":
    unittest.main()
