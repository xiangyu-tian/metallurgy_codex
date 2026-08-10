import copy
import unittest

from Tools.core_freeze.e3_routing import run_e3_a004_hardcase_development as runner


class V11Cf05E3A004HardcaseRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = runner.load_json(runner.CONFIG_PATH)
        cls.opening = runner.validate_opening(cls.config)

    def test_opening_grid_and_policy_are_frozen(self):
        self.assertEqual(len(self.opening["tasks"]), 2)
        self.assertEqual(len(self.opening["views"]), 42)
        self.assertEqual(len(self.opening["cells"]), 48)
        self.assertFalse(self.config["tool_execution_allowed"])
        self.assertFalse(self.config["provider_retry_allowed"])
        self.assertFalse(self.config["independent_validation_split_access_allowed"])

    def test_payload_contains_only_task_prompt_and_submitted_schemas(self):
        cell = self.opening["cells"][0]
        payload = runner.payload_for(cell, self.opening["task_by_id"], self.opening["view_by_id"],
                                     self.opening["prompt"], self.config)
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(len(payload["messages"]), 2)
        self.assertEqual(len(payload["tools"]), cell["selector_schema_count"])

    def test_policy_escalation_is_rejected(self):
        for field in ("tool_execution_allowed", "provider_retry_allowed",
                      "independent_validation_split_access_allowed", "confirmatory_inference_allowed",
                      "core_frozen"):
            invalid = copy.deepcopy(self.config)
            invalid[field] = True
            with self.assertRaisesRegex(ValueError, "must remain false|exactly one provider attempt"):
                runner.validate_opening(invalid)

    def test_response_parser_never_executes_tools(self):
        response = {"choices": [{"message": {"content": None, "tool_calls": [{"function": {
            "name": "A004", "arguments": '{"compositions":{"matrix":999.0,"trace":1.0}}'}}]}}]}
        parsed = runner.parse_response(response)
        self.assertTrue(parsed["exactly_one_tool_call"])
        self.assertEqual(parsed["selected_tool_id"], "A004")
        self.assertTrue(parsed["arguments_json_valid"])


if __name__ == "__main__":
    unittest.main()
