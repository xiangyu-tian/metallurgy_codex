import json
import unittest

from Tools.core_freeze.e3_routing import a004_contract_adjudication as gate
from Tools.core_freeze.e3_routing import run_e3_a004_postgate_probe as runtime


class V11Cf05E3A004PostgateProbeRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = gate.load_json(runtime.CONFIG_PATH)
        cls.opening = runtime.validate_opening(cls.config)

    def test_runtime_is_exactly_ten_one_shot_cells(self):
        self.assertEqual(len(self.opening["cells"]), 10)
        self.assertEqual(self.config["provider_max_attempts"], 1)
        self.assertFalse(self.config["provider_retry_allowed"])
        self.assertFalse(self.config["tool_execution_allowed"])

    def test_payload_uses_frozen_prompt_and_schema(self):
        payload = runtime.payload_for(self.opening["cells"][0], self.opening, self.config)
        self.assertEqual(payload["model"], "deepseek-v4-flash")
        self.assertEqual([tool["function"]["name"] for tool in payload["tools"]], runtime.EXPECTED_TOOL_IDS)
        self.assertEqual(payload["tool_choice"], "auto")

    def test_raw_and_gate_views_are_separate(self):
        response = {"choices": [{"message": {"tool_calls": [
            {"function": {"name": "A004", "arguments": json.dumps({"compositions": {"binder": 12.5, "inclusion": 0.5}})}}
        ]}}]}
        summary = runtime.raw_summary(response)
        decision = gate.adjudicate(self.opening["tasks"][0]["problem_text"], response, self.opening["profiles"])
        self.assertEqual(summary["called_tool_ids"], ["A004"])
        self.assertEqual(decision["decision"], "allow_original_single_call")
        self.assertNotIn("gate_decision", summary)

    def test_runtime_config_rejects_policy_escalation(self):
        changed = dict(self.config)
        changed["tool_execution_allowed"] = True
        with self.assertRaisesRegex(ValueError, "must remain false"):
            runtime.validate_opening(changed)


if __name__ == "__main__":
    unittest.main()
