import json
import shutil
import unittest
import uuid

from Tools.core_freeze.e3_routing import analyze_e3_multitarget_mixed_development as analysis


class V11Cf05E3MultitargetAnalysisTests(unittest.TestCase):
    def test_optional_schema_default_is_semantically_compatible(self):
        expected = {"value": 1.0}
        schema = {
            "type": "object",
            "properties": {
                "value": {"type": "number"},
                "label": {"type": "string", "default": "B"},
            },
        }
        self.assertTrue(
            analysis.parameters_compatible(
                {"value": 1, "label": "B"}, expected, schema
            )
        )
        self.assertFalse(
            analysis.parameters_compatible(
                {"value": 1, "label": "C"}, expected, schema
            )
        )
        self.assertFalse(
            analysis.parameters_compatible(
                {"value": 1, "unknown": "B"}, expected, schema
            )
        )

    def test_frozen_r2_results_score_all_cells(self):
        built = analysis.build(analysis.load_json(analysis.CONFIG_PATH))
        self.assertEqual(len(built["rows"]), 64)
        self.assertEqual(built["report"]["overall"]["acceptable_tool_selection_accuracy"], 1)
        self.assertEqual(built["report"]["overall"]["parameter_accuracy"], 1)
        self.assertEqual(built["report"]["overall"]["complete_call_accuracy"], 1)
        self.assertTrue(built["report"]["ceiling_observed"])

    def test_output_manifest_binds_all_analysis_artifacts(self):
        output_dir = (
            analysis.WORKSPACE / "outputs" / f".multitarget-analysis-test-{uuid.uuid4().hex}"
        )
        try:
            report = analysis.build_outputs(output_dir)
            self.assertEqual(report["result_count"], 64)
            manifest = analysis.load_json(output_dir / "artifact_manifest.json")
            self.assertEqual(manifest["artifact_count"], 3)
            for row in manifest["artifacts"]:
                self.assertEqual(
                    analysis.file_hash(output_dir / row["filename"]), row["sha256"]
                )
        finally:
            if output_dir.exists():
                shutil.rmtree(output_dir)


if __name__ == "__main__":
    unittest.main()
