import hashlib
import json
import unittest

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common
from Tools.core_freeze.e3_routing import a001_a002_strict_parameter_gate as gate


class V11Cf05E3A001A002StrictParameterGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = gate.audit_and_replay(common.load_json(gate.CONFIG_PATH))

    def test_all_observed_calls_are_request_grounded(self):
        report = self.result["report"]
        self.assertEqual(report["cell_count"], 32)
        self.assertEqual(report["unique_task_count"], 4)
        self.assertEqual(report["strict_parameter_evidence_fidelity_count"], 32)
        self.assertEqual(report["execution_ready_count"], 32)
        self.assertEqual(report["review_required_count"], 0)
        self.assertFalse(report["gold_used_during_decision"])

    def test_both_tools_have_complete_balanced_replay(self):
        for tool_id in ("A001", "A002"):
            with self.subTest(tool_id=tool_id):
                row = self.result["report"]["by_tool"][tool_id]
                self.assertEqual(row["cell_count"], 16)
                self.assertEqual(row["unique_task_count"], 2)
                self.assertEqual(row["strict_parameter_evidence_fidelity_count"], 16)

    def test_all_boundary_challenges_pass(self):
        report = self.result["report"]
        self.assertEqual(report["challenge_case_count"], 16)
        self.assertEqual(report["challenge_passed_count"], 16)

    def test_unverified_unit_pair_requires_review(self):
        row = next(row for row in self.result["challenge_rows"] if row["case_id"] == "A001-UNVERIFIED-PAIR")
        self.assertEqual(row["decision"]["decision"], "review_required")
        self.assertIn("unit_pair_outside_verified_contract", row["decision"]["vetoes"])

    def test_invalid_formula_requires_review(self):
        row = next(row for row in self.result["challenge_rows"] if row["case_id"] == "A002-INVALID-GRAMMAR")
        self.assertEqual(row["decision"]["decision"], "review_required")
        self.assertIn("formula_outside_verified_neutral_grammar", row["decision"]["vetoes"])

    def test_formal_schemas_close_unknown_properties(self):
        for tool_id in ("A001", "A002"):
            with self.subTest(tool_id=tool_id):
                parameters = self.result["formal_schemas"][tool_id]["openai_tool"]["function"]["parameters"]
                self.assertIs(parameters["additionalProperties"], False)
                self.assertEqual(
                    set(parameters["required"]),
                    set(common.load_json(gate.CONFIG_PATH)["target_tools"][tool_id]["required_parameters"]),
                )

    def test_no_runtime_or_external_execution_occurred(self):
        report = self.result["report"]
        self.assertFalse(report["runtime_mutation_required"])
        self.assertEqual(report["tool_calls_executed"], 0)
        self.assertEqual(report["external_api_calls"], 0)

    def test_manifest_matches_outputs(self):
        output_dir = common.WORKSPACE / "outputs/v11_cf05_e3_a001_a002_strict_parameter_gate_v1_20260811"
        manifest = json.loads((output_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["artifact_count"], 9)
        for row in manifest["artifacts"]:
            path = output_dir / row["filename"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])


if __name__ == "__main__":
    unittest.main()
