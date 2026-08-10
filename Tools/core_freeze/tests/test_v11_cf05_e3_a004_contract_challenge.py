import hashlib
import json
import unittest

from Tools.core_freeze.e3_routing import a004_contract_adjudication as gate
from Tools.core_freeze.e3_routing import a004_contract_adjudication_challenge as challenge_runner


class V11Cf05E3A004ContractChallengeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.challenge = gate.load_json(challenge_runner.CHALLENGE_PATH)
        cls.profiles = gate.load_bound_profile_registry(gate.load_json(gate.CONFIG_PATH))
        cls.result = challenge_runner.run_challenge(cls.challenge, cls.profiles)

    def test_challenge_has_unique_cases_and_boundary_coverage(self):
        case_ids = [row["case_id"] for row in self.challenge["cases"]]
        categories = {row["category"] for row in self.challenge["cases"]}
        self.assertEqual(len(case_ids), 15)
        self.assertEqual(len(case_ids), len(set(case_ids)))
        self.assertTrue({
            "zero_call", "unknown_tool", "invalid_arguments_json", "parameter_mismatch",
            "normalization_mismatch", "candidate_not_execution_eligible",
            "unique_contract_adjudication", "non_unique_duplicate_calls",
            "duplicate_tool_argument_binding", "no_compatible_candidate",
            "incomplete_candidate_evidence",
        }.issubset(categories))

    def test_all_challenge_cases_pass(self):
        self.assertEqual(self.result["report"]["passed_count"], 15)
        self.assertEqual(self.result["report"]["failed_count"], 0)
        self.assertEqual(self.result["report"]["pass_rate"], 1.0)

    def test_expected_fields_never_enter_decision_input(self):
        self.assertTrue(all(row["decision_input_fields"] == ["problem_text", "raw_response"]
                            for row in self.result["rows"]))
        self.assertFalse(self.result["report"]["gold_accessed_during_decision"])

    def test_duplicate_tool_selection_keeps_the_compatible_call_arguments(self):
        row = next(row for row in self.result["rows"] if row["case_id"] == "CG-011-DUPLICATE-ONE-VALID")
        self.assertEqual(row["decision"]["selected_arguments"], {"compositions": {"x": 2.0, "y": 3.0}})

    def test_unknown_or_malformed_companion_forces_review(self):
        for case_id in ("CG-013-VALID-PLUS-UNKNOWN", "CG-014-VALID-PLUS-MALFORMED"):
            row = next(row for row in self.result["rows"] if row["case_id"] == case_id)
            self.assertEqual(row["decision"]["decision"], "review_required")
            self.assertEqual(row["decision"]["decision_reason"], "candidate_evidence_incomplete")

    def test_original_144_response_replay_remains_complete(self):
        replay = gate.build(gate.load_json(gate.CONFIG_PATH))["report"]
        self.assertEqual(replay["post_gate_complete_call_correct_count"], 144)
        self.assertEqual(replay["original_single_call_false_block_count"], 0)

    def test_committed_manifest_matches_files(self):
        output_dir = gate.WORKSPACE / "outputs/v11_cf05_e3_a004_contract_gate_challenge_v1_20260810"
        manifest = json.loads((output_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["artifact_count"], 4)
        for row in manifest["artifacts"]:
            path = output_dir / row["filename"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])
            self.assertEqual(path.stat().st_size, row["bytes"])


if __name__ == "__main__":
    unittest.main()
