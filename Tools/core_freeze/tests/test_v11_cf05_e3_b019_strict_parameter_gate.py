import hashlib
import json
import unittest

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common
from Tools.core_freeze.e3_routing import b019_strict_parameter_gate as gate


class V11Cf05E3B019StrictParameterGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = gate.replay(common.load_json(gate.CONFIG_PATH))

    def test_replay_repairs_parameter_candidates_without_gold_decision_input(self):
        report = self.result["report"]
        self.assertEqual(report["replay_cell_count"], 16)
        self.assertEqual(report["original_parameter_faithful_count"], 5)
        self.assertEqual(report["optional_elision_count"], 11)
        self.assertEqual(report["candidate_parameter_faithful_count"], 16)
        self.assertFalse(report["gold_used_during_decision"])

    def test_runtime_default_risk_blocks_formal_execution(self):
        report = self.result["report"]
        self.assertEqual(report["runtime_default_component_risk_count"], 16)
        self.assertEqual(report["execution_ready_count"], 0)
        self.assertTrue(all(not row["execution_ready"] for row in self.result["rows"]))

    def test_all_boundary_challenges_pass(self):
        report = self.result["report"]
        self.assertEqual(report["challenge_case_count"], 12)
        self.assertEqual(report["challenge_passed_count"], 12)

    def test_unparseable_and_physical_invalid_cases_require_review(self):
        for category in ("unparseable_request", "equal_phase_endpoints", "overall_outside_tieline"):
            row = next(row for row in self.result["challenge_rows"] if row["category"] == category)
            self.assertEqual(row["decision"]["decision"], "review_required")

    def test_explicit_component_can_be_execution_ready(self):
        row = next(row for row in self.result["challenge_rows"] if row["category"] == "explicit_component")
        self.assertEqual(row["decision"]["decision"], "candidate_pass_original_parameters")
        self.assertTrue(row["decision"]["execution_ready"])

    def test_manifest_matches_outputs(self):
        output_dir = common.WORKSPACE / "outputs/v11_cf05_e3_b019_strict_parameter_gate_v1_20260811"
        manifest = json.loads((output_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["artifact_count"], 5)
        for row in manifest["artifacts"]:
            path = output_dir / row["filename"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])


if __name__ == "__main__":
    unittest.main()
