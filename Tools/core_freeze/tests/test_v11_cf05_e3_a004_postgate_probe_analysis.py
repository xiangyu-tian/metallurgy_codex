import hashlib
import json
import unittest

from Tools.core_freeze.e3_routing import a004_contract_adjudication as gate
from Tools.core_freeze.e3_routing import analyze_e3_a004_postgate_probe as analysis


class V11Cf05E3A004PostgateProbeAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = analysis.analyze(gate.load_json(analysis.CONFIG_PATH))

    def test_all_raw_calls_are_complete_and_correct(self):
        report = self.result["report"]
        self.assertEqual(report["raw_exactly_one_call_count"], 10)
        self.assertEqual(report["raw_selection_correct_count"], 10)
        self.assertEqual(report["raw_parameters_correct_count"], 10)
        self.assertEqual(report["raw_complete_call_correct_count"], 10)

    def test_gate_does_not_false_block_correct_calls(self):
        report = self.result["report"]
        self.assertEqual(report["gate_complete_call_correct_count"], 10)
        self.assertEqual(report["gate_intervention_count"], 0)
        self.assertEqual(report["gate_false_block_count"], 0)

    def test_execution_scope_remains_exact(self):
        report = self.result["report"]
        self.assertEqual(report["external_api_calls"], 10)
        self.assertEqual(report["tool_calls_executed"], 0)
        self.assertEqual(report["retries_executed"], 0)
        self.assertFalse(report["causal_gate_benefit_claim_allowed"])

    def test_manifest_matches_outputs(self):
        output_dir = gate.WORKSPACE / "outputs/v11_cf05_e3_a004_postgate_probe_analysis_20260810"
        manifest = json.loads((output_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["artifact_count"], 3)
        for row in manifest["artifacts"]:
            path = output_dir / row["filename"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])


if __name__ == "__main__":
    unittest.main()
