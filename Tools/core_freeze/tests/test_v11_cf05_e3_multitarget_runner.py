import copy
import shutil
import unittest
import uuid
from datetime import datetime, timezone

from Tools.core_freeze.e3_routing import run_e3_multitarget_mixed_development as runner
from Tools.models_core.llm_adapters import DeepSeekOpenAIAdapter


class V11Cf05E3MultitargetRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = runner.load_json(runner.CONFIG_PATH)
        cls.opening = runner.validate_opening(cls.config)
        cls.temp_dir = (
            runner.WORKSPACE
            / "outputs"
            / f".multitarget-runner-test-{uuid.uuid4().hex}"
        )
        cls.auth_path = (
            cls.temp_dir.parent / f".{cls.temp_dir.name}-authorization.json"
        )
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
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 1,
                    "total_tokens": 11,
                },
            }

        cls.adapter = DeepSeekOpenAIAdapter(
            api_key="test-only",
            base_url=cls.config["openai_base_url"],
            model=cls.config["model"],
            thinking=cls.config["thinking"],
            transport=fake_transport,
        )
        cls.report = runner.build_outputs(cls.auth_path, cls.temp_dir, cls.adapter)

    @classmethod
    def make_authorization(cls):
        return {
            "schema_version": "1.0",
            "run_id": runner.EXPECTED_RUN_ID,
            "opening_id": runner.EXPECTED_OPENING_ID,
            "decision": runner.EXPECTED_DECISION,
            "provider": cls.config["provider"],
            "endpoint": cls.config["openai_base_url"],
            "model": cls.config["model"],
            "scheduled_request_count": 64,
            "opening_manifest_sha256": runner.file_hash(
                cls.opening["paths"]["opening_manifest"]
            ),
            "runtime_config_sha256": runner.file_hash(runner.CONFIG_PATH),
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

    def test_all_64_requests_complete_without_tool_execution(self):
        self.assertEqual(self.report["scheduled_request_count"], 64)
        self.assertEqual(self.report["external_api_calls"], 64)
        self.assertEqual(self.report["transport_accepted_count"], 64)
        self.assertEqual(self.report["exactly_one_tool_call_count"], 64)
        self.assertEqual(self.report["tool_calls_executed"], 0)
        self.assertEqual(self.report["retries_executed"], 0)

    def test_results_and_manifest_are_complete(self):
        results = runner.load_json(self.temp_dir / "multitarget_request_results.json")
        self.assertEqual(results["result_count"], 64)
        self.assertEqual(len({row["cell_id"] for row in results["results"]}), 64)
        self.assertTrue(all(row["tool_executed"] is False for row in results["results"]))
        manifest = runner.load_json(self.temp_dir / "artifact_manifest.json")
        self.assertEqual(manifest["artifact_count"], 5)
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
                runner.validate_authorization(invalid, self.config, self.opening)

    def test_payloads_preserve_frozen_schema_order_and_safety(self):
        for cell in self.opening["cells"]:
            payload = runner.payload_for(
                cell,
                self.opening["task_by_id"],
                self.opening["view_by_id"],
                self.opening["prompt"],
                self.config,
            )
            view = self.opening["view_by_id"][cell["candidate_view_id"]]
            self.assertEqual(
                [tool["function"]["name"] for tool in payload["tools"]],
                view["ordered_candidate_tool_ids"],
            )
            self.assertEqual(payload["thinking"], {"type": self.config["thinking"]})
            self.assertNotIn("expected_tool", runner.canonical_json(payload))
            self.assertNotIn("acceptable_tools", runner.canonical_json(payload))


if __name__ == "__main__":
    unittest.main()
