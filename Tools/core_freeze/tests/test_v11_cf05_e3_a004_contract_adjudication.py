import copy
import hashlib
import json
from pathlib import Path
import unittest

from Tools.core_freeze.e3_routing import a004_contract_adjudication as gate


class V11Cf05E3A004ContractAdjudicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = gate.load_json(gate.CONFIG_PATH)
        cls.result = gate.build(cls.config)

    def test_requirement_parser_distinguishes_unit_sum_and_labels(self):
        req = gate.extract_requirements('组分 {"matrix": 0.9, "trace": 0.1}，归一化使总和为1，保留6位。')
        self.assertEqual(req["normalization_kind"], "unit_sum")
        self.assertTrue(req["generic_labels_present"])
        self.assertEqual(req["precision_digits"], 6)

    def test_gold_is_not_an_adjudicator_input(self):
        safety = self.result["safety"]
        self.assertNotIn("offline_scoring_registry", safety["semantic_gate_inputs"])
        self.assertIn("acceptable_tools", safety["semantic_gate_forbidden_inputs"])
        self.assertFalse(self.result["report"]["gold_used_during_decision"])

    def test_all_three_stable_failures_are_safely_resolved(self):
        events = self.result["adjudicated_events"]
        self.assertEqual(len(events), 3)
        self.assertTrue(all(row["original_called_tool_ids"] == ["A004", "E3C005", "E3C027"] for row in events))
        self.assertTrue(all(row["selected_tool_id"] == "A004" for row in events))
        self.assertTrue(all(row["original_execution_blocked"] for row in events))
        self.assertTrue(all(row["offline_evaluation_only"]["complete_call_correct"] for row in events))

    def test_original_single_calls_are_not_false_blocked(self):
        report = self.result["report"]
        self.assertEqual(report["original_structure_violation_count"], 3)
        self.assertEqual(report["unsafe_multi_call_execution_prevented_count"], 3)
        self.assertEqual(report["original_single_call_false_block_count"], 0)
        self.assertEqual(report["post_gate_complete_call_correct_count"], 144)
        self.assertFalse(report["raw_model_outcomes_modified"])

    def test_unresolved_ambiguity_requires_review(self):
        profiles = copy.deepcopy(self.result["profiles"])
        for row in profiles["profiles"]:
            row["execution_eligible"] = True
            row["formal_execution_allowed"] = True
            row["normalization_kind"] = "unit_sum"
            row["label_domain"] = "generic_numeric_components"
        raw = {"choices": [{"message": {"tool_calls": [
            {"function": {"name": "A004", "arguments": '{"compositions":{"x":1}}'}},
            {"function": {"name": "E3C005", "arguments": '{"compositions":{"x":1}}'}}
        ]}}]}
        decision = gate.adjudicate('将 {"x":1} 归一化使总和为1', raw, profiles)
        self.assertEqual(decision["decision"], "review_required")
        self.assertEqual(decision["output_tool_call_count"], 0)

    def test_policy_escalations_are_rejected(self):
        for field in ("gold_access_allowed_during_decision", "tool_execution_allowed",
                      "external_api_calls_authorized", "automatic_retry_allowed",
                      "confirmatory_inference_allowed", "core_frozen"):
            invalid = copy.deepcopy(self.config)
            invalid[field] = True
            with self.assertRaisesRegex(ValueError, "must remain false"):
                gate.build(invalid)

    def test_committed_artifact_manifest_matches_files(self):
        output_dir = gate.WORKSPACE / "outputs/v11_cf05_e3_a004_contract_gate_candidate_v1_20260810"
        manifest = json.loads((output_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["artifact_count"], 8)
        self.assertEqual(len(manifest["artifacts"]), 8)
        for row in manifest["artifacts"]:
            path = output_dir / row["filename"]
            self.assertTrue(path.is_file())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])
            self.assertEqual(path.stat().st_size, row["bytes"])


if __name__ == "__main__":
    unittest.main()
