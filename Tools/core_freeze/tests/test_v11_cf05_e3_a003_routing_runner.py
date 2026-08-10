import copy
import json
import shutil
import unittest
import uuid
from datetime import datetime, timezone

from Tools.core_freeze.e3_routing import run_e3_a003_routing_development as runner
from Tools.models_core.llm_adapters import DeepSeekOpenAIAdapter


class V11Cf05E3A003RoutingRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.opening_dir = (
            runner.WORKSPACE
            / "outputs"
            / "v11_cf05_e3_a003_routing_execution_opening_v1_20260809"
        )
        cls.opening = runner.validate_opening(cls.opening_dir)
        cls.temp_dir = runner.WORKSPACE / "outputs" / f".a003-runner-test-{uuid.uuid4().hex}"
        cls.auth_path = cls.temp_dir.parent / f".{cls.temp_dir.name}-authorization.json"
        cls.authorization = cls.make_authorization()
        runner.write_json(cls.auth_path, cls.authorization)

        def fake_transport(url, headers, payload, timeout):
            selected = payload["tools"][0]["function"]["name"]
            return {
                "id": "fake-response",
                "model": payload["model"],
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "fake-call",
                                    "type": "function",
                                    "function": {
                                        "name": selected,
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
            }

        cls.adapter = DeepSeekOpenAIAdapter(
            api_key="test-only",
            base_url=cls.opening["config"]["openai_base_url"],
            model=cls.opening["config"]["model"],
            thinking=cls.opening["config"]["thinking"],
            transport=fake_transport,
        )
        cls.report = runner.build_outputs(
            cls.opening_dir, cls.auth_path, cls.temp_dir, cls.adapter
        )

    @classmethod
    def make_authorization(cls):
        paths = cls.opening["paths"]
        config = cls.opening["config"]
        return {
            "schema_version": "1.0",
            "opening_id": runner.EXPECTED_OPENING_ID,
            "decision": runner.EXPECTED_DECISION,
            "provider": config["provider"],
            "endpoint": config["openai_base_url"],
            "model": config["model"],
            "scheduled_request_count": 96,
            "opening_manifest_sha256": runner.file_hash(paths["manifest"]),
            "config_sha256": runner.file_hash(paths["config"]),
            "blueprints_sha256": runner.file_hash(paths["blueprints"]),
            "schema_views_sha256": runner.file_hash(paths["schema_views"]),
            "runner_sha256": runner.file_hash(runner.Path(runner.__file__)),
            "external_data_sharing_authorized": True,
            "external_api_execution_authorized": True,
            "tool_execution_authorized": False,
            "provider_retry_authorized": False,
            "independent_validation_split_access_authorized": False,
            "confirmatory_inference_allowed": False,
            "core_frozen": False,
            "authorized_by": "unit-test",
            "authorized_at": datetime.now(timezone.utc).isoformat(),
            "authorization_basis": "unit-test fake transport only",
        }

    @classmethod
    def tearDownClass(cls):
        if cls.temp_dir.exists():
            shutil.rmtree(cls.temp_dir)
        cls.auth_path.unlink(missing_ok=True)

    def test_all_96_requests_complete_without_tool_execution(self):
        self.assertEqual(self.report["scheduled_request_count"], 96)
        self.assertEqual(self.report["external_api_calls"], 96)
        self.assertEqual(self.report["transport_accepted_count"], 96)
        self.assertEqual(self.report["exactly_one_tool_call_count"], 96)
        self.assertEqual(self.report["tool_calls_executed"], 0)
        self.assertEqual(self.report["retries_executed"], 0)

    def test_results_and_manifest_are_complete(self):
        results = runner.load_json(self.temp_dir / "a003_routing_request_results.json")
        self.assertEqual(results["result_count"], 96)
        self.assertEqual(len({row["cell_id"] for row in results["results"]}), 96)
        self.assertTrue(all(row["tool_executed"] is False for row in results["results"]))
        manifest = runner.load_json(self.temp_dir / "artifact_manifest.json")
        self.assertEqual(manifest["artifact_count"], 7)
        for row in manifest["artifacts"]:
            path = self.temp_dir / row["filename"]
            self.assertEqual(runner.file_hash(path), row["sha256"])

    def test_authorization_policy_changes_are_rejected(self):
        for field, value in (
            ("tool_execution_authorized", True),
            ("provider_retry_authorized", True),
            ("confirmatory_inference_allowed", True),
            ("independent_validation_split_access_authorized", True),
        ):
            invalid = copy.deepcopy(self.authorization)
            invalid[field] = value
            with self.assertRaisesRegex(ValueError, "policy mismatch"):
                runner.validate_authorization(invalid, self.opening, self.auth_path)

    def test_wire_payload_hashes_are_rechecked(self):
        for cell in self.opening["blueprints"]["cells"]:
            payload = runner.reconstruct_payload(
                cell, self.opening["schema_by_id"], self.opening["system_prompt"]
            )
            self.assertEqual(runner.json_hash(payload), cell["request_body_sha256"])


if __name__ == "__main__":
    unittest.main()
