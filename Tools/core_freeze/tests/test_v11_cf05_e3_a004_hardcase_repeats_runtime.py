import copy
import unittest

from Tools.core_freeze.e3_routing import run_e3_a004_hardcase_repeats as runner


class V11Cf05E3A004HardcaseRepeatsRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = runner.load_json(runner.CONFIG_PATH)
        cls.opening = runner.validate_opening(cls.config)

    def test_repeat_order_and_dimensions_are_frozen(self):
        cells = self.opening["cells"]
        self.assertEqual(len(cells), 96)
        self.assertEqual([row["model_run_repeat"] for row in cells], [2] * 48 + [3] * 48)
        self.assertEqual(len(self.opening["tasks"]), 2)
        self.assertEqual(len(self.opening["views"]), 42)

    def test_payload_contract_matches_r1(self):
        cell = self.opening["cells"][0]
        payload = runner.payload_for(cell, self.opening["task_by_id"], self.opening["view_by_id"],
                                     self.opening["prompt"], self.config)
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertEqual(len(payload["tools"]), cell["selector_schema_count"])

    def test_policy_escalation_is_rejected(self):
        for field in ("tool_execution_allowed", "provider_retry_allowed",
                      "independent_validation_split_access_allowed", "confirmatory_inference_allowed",
                      "core_frozen"):
            invalid = copy.deepcopy(self.config)
            invalid[field] = True
            with self.assertRaisesRegex(ValueError, "must remain false|one provider attempt"):
                runner.validate_opening(invalid)

    def test_committed_repeat_output_is_hash_complete(self):
        output_dir = runner.WORKSPACE / "outputs" / "v11_cf05_e3_a004_hardcase_r2r3_20260810"
        report = runner.load_json(output_dir / "a004_r2r3_runtime_report.json")
        self.assertEqual(report["external_api_calls"], 96)
        self.assertEqual(report["transport_accepted_count"], 96)
        self.assertEqual(report["exactly_one_tool_call_count"], 94)
        self.assertEqual([row["exactly_one_tool_call_count"] for row in report["by_repeat"]], [47, 47])
        self.assertEqual(report["tool_calls_executed"], 0)
        self.assertEqual(report["retries_executed"], 0)
        manifest = runner.load_json(output_dir / "artifact_manifest.json")
        self.assertEqual(manifest["artifact_count"], 5)
        for row in manifest["artifacts"]:
            path = output_dir / row["filename"]
            self.assertTrue(path.is_file())
            self.assertEqual(runner.file_hash(path), row["sha256"])


if __name__ == "__main__":
    unittest.main()
