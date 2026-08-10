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


if __name__ == "__main__":
    unittest.main()
