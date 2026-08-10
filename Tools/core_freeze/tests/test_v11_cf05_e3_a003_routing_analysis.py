import copy
import json
import shutil
import unittest
import uuid

from Tools.core_freeze.e3_routing import analyze_e3_a003_routing_development as analyzer


class V11Cf05E3A003RoutingAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = analyzer.load_json(analyzer.CONFIG_PATH)
        cls.built = analyzer.build(cls.config)

    def test_all_runtime_and_gold_inputs_are_hash_bound(self):
        for binding in self.config["bindings"].values():
            analyzer.validate_binding(binding)

    def test_all_96_cells_score_correctly(self):
        rows = self.built["rows"]
        self.assertEqual(len(rows), 96)
        self.assertTrue(all(row["selection_correct"] for row in rows))
        self.assertTrue(all(row["parameters_correct"] for row in rows))
        self.assertTrue(all(row["complete_call_correct"] for row in rows))
        self.assertTrue(all(row["selected_tool_visible"] for row in rows))
        self.assertTrue(all(row["tool_executed"] is False for row in rows))

    def test_four_method_summaries_remain_descriptive(self):
        report = self.built["report"]
        self.assertEqual(len(report["by_method"]), 4)
        for row in report["by_method"]:
            self.assertEqual(row["cell_count"], 24)
            self.assertEqual(row["complete_call_accuracy"], 1.0)
        self.assertEqual(report["selected_tool_counts"], {"A003": 96})
        self.assertFalse(report["confirmatory_inference_allowed"])
        self.assertFalse(report["core_frozen"])

    def test_size_and_neighbor_effects_are_not_overinterpreted(self):
        for row in self.built["report"]["descriptive_effects"]:
            self.assertEqual(row["accuracy_120_minus_17"], 0.0)
            self.assertEqual(row["functional_8_minus_lexical_8"], 0.0)
            self.assertEqual(
                row["interpretation"],
                "development_descriptive_only_no_confirmatory_inference",
            )

    def test_policy_mutations_are_rejected(self):
        for field in ("confirmatory_inference_allowed", "core_frozen"):
            invalid = copy.deepcopy(self.config)
            invalid[field] = True
            with self.assertRaisesRegex(ValueError, "cannot become confirmatory"):
                analyzer.build(invalid)

    def test_fresh_output_manifest_is_complete(self):
        output_dir = analyzer.WORKSPACE / "outputs" / f".a003-analysis-test-{uuid.uuid4().hex}"
        try:
            analyzer.build_outputs(output_dir)
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["artifact_count"], 3)
            for row in manifest["artifacts"]:
                path = output_dir / row["filename"]
                self.assertEqual(analyzer.file_hash(path), row["sha256"])
        finally:
            if output_dir.exists():
                shutil.rmtree(output_dir)


if __name__ == "__main__":
    unittest.main()
