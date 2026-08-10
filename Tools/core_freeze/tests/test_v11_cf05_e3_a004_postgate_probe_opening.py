import hashlib
import json
import unittest

from Tools.core_freeze.e3_routing import a004_contract_adjudication as gate
from Tools.core_freeze.e3_routing import build_e3_a004_postgate_probe_opening as opening


class V11Cf05E3A004PostgateProbeOpeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = gate.load_json(opening.CONFIG_PATH)
        cls.built = opening.build(cls.config)

    def test_ten_router_blind_probe_tasks_are_frozen(self):
        tasks = self.built["tasks"]
        self.assertEqual(tasks["task_count"], 10)
        self.assertFalse(tasks["gold_fields_present"])
        self.assertEqual(len({row["task_id"] for row in tasks["tasks"]}), 10)

    def test_schema_view_is_the_frozen_five_tool_order(self):
        view = self.built["schema_view"]
        self.assertEqual(view["ordered_candidate_tool_ids"], self.config["expected_tool_ids"])
        self.assertEqual(len(view["openai_tools"]), 5)

    def test_router_artifacts_have_no_gold_keys(self):
        for name in ("tasks", "schema_view", "prompt", "run_cells"):
            self.assertFalse(opening.contains_forbidden_key(self.built[name]), name)

    def test_scoring_is_offline_and_parameters_come_from_request(self):
        scoring = self.built["scoring"]
        self.assertFalse(scoring["router_visible"])
        for task, gold in zip(self.built["tasks"]["tasks"], scoring["tasks"], strict=True):
            self.assertEqual(gold["expected_parameters"]["compositions"],
                             gate.first_json_object(task["problem_text"]))

    def test_opening_remains_unexecuted_and_unauthorized(self):
        auth = self.built["authorization"]
        preflight = self.built["preflight"]
        self.assertEqual(auth["decision"], "pending_user_authorization")
        self.assertFalse(auth["external_api_execution_authorized"])
        self.assertFalse(auth["tool_execution_allowed"])
        self.assertEqual(preflight["external_api_calls"], 0)

    def test_manifest_matches_committed_outputs(self):
        output_dir = gate.WORKSPACE / "outputs/v11_cf05_e3_a004_postgate_probe_opening_v1_20260810"
        manifest = json.loads((output_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["artifact_count"], 8)
        for row in manifest["artifacts"]:
            path = output_dir / row["filename"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])
            self.assertEqual(path.stat().st_size, row["bytes"])


if __name__ == "__main__":
    unittest.main()
