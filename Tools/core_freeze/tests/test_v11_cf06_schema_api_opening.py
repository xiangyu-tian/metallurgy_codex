import copy
import json
import shutil
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from Tools.core_freeze.cf06_schema_api import build_cf06_schema_api_opening as builder
from Tools.core_freeze.cf06_schema_api import run_cf06_schema_feasibility as runner


class FakeAdapter:
    def __init__(self, config):
        self.api_key = "test-only-key"
        self.base_url = config["openai_base_url"]
        self.model = config["model"]
        self.thinking = config["thinking"]
        self.timeout = float(config["timeout_seconds"])
        self.calls = []

    def ensure_ready(self):
        return None

    def transport(self, url, headers, payload, timeout):
        self.calls.append(
            {
                "url": url,
                "authorization_header_present": bool(headers.get("Authorization")),
                "payload": copy.deepcopy(payload),
                "timeout": timeout,
            }
        )
        tools = payload.get("tools", [])
        tool_count = len(tools)
        prompt_tokens = 40 + len(runner.canonical_json(payload["messages"])) // 4
        prompt_tokens += len(runner.canonical_json(tools)) // 4
        if payload.get("tool_choice") == "auto":
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"fake-{tool_count}",
                        "type": "function",
                        "function": {
                            "name": "A003",
                            "arguments": '{"formula":"Fe2O3"}',
                        },
                    }
                ],
            }
            finish_reason = "tool_calls"
        elif payload.get("tool_choice") == "none":
            message = {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "target_tool_visible": True,
                        "target_tool_id": "A003",
                        "declared_tool_count": tool_count,
                    }
                ),
            }
            finish_reason = "stop"
        else:
            message = {"role": "assistant", "content": "{}"}
            finish_reason = "stop"
        return {
            "id": f"fake-response-{len(self.calls)}",
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": finish_reason,
                    "message": message,
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": 8,
                "total_tokens": prompt_tokens + 8,
            },
        }


@contextmanager
def workspace_test_directory():
    path = builder.WORKSPACE / "outputs" / f".cf06-test-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path)


class V11Cf06SchemaApiOpeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = builder.load_json(builder.CONFIG_PATH)
        cls.prompts = builder.load_json(builder.PROMPTS_PATH)
        cls.built = builder.build(cls.config, cls.prompts)

    def test_none_prompt_renders_literal_json_contract(self):
        messages = builder.messages_for(
            self.prompts,
            "none_schema_visibility",
            "Fe2O3",
            120,
        )
        user = messages[1]["content"]
        self.assertIn('"target_tool_visible":true或false', user)
        self.assertIn('"declared_tool_count":整数', user)
        self.assertIn("本次预期工具数为 120", user)

    def test_catalog_and_all_pool_artifacts_are_hash_bound(self):
        catalog_dir, manifest = builder.validate_catalog_manifest(self.config)
        self.assertEqual(manifest["artifact_count"], 8)
        for row in manifest["artifacts"]:
            path = catalog_dir / row["filename"]
            self.assertEqual(builder.file_hash(path), row["sha256"])
            self.assertEqual(path.stat().st_size, row["bytes"])

    def test_request_bundle_has_two_baselines_and_eight_probes(self):
        requests = self.built["request_bundle"]["requests"]
        self.assertEqual(len(requests), 10)
        self.assertEqual(
            [row["request_kind"] for row in requests[:2]],
            ["same_prompt_no_tools_baseline"] * 2,
        )
        probes = [
            row for row in requests if row["request_kind"] == "full_schema_api_probe"
        ]
        self.assertEqual(len(probes), 8)
        self.assertEqual(
            {
                (row["tool_count"], row["probe_mode"])
                for row in probes
            },
            {
                (size, mode)
                for size in [17, 50, 100, 120]
                for mode in ["auto_function_call", "none_schema_visibility"]
            },
        )

    def test_payloads_preserve_exact_tool_count_and_never_contain_api_key(self):
        bundle = self.built["request_bundle"]
        self.assertNotIn("api_key", builder.canonical_json(bundle).lower())
        for row in bundle["requests"]:
            tools = row["payload"].get("tools", [])
            self.assertEqual(len(tools), row["tool_count"])
            self.assertEqual(
                builder.json_hash(row["payload"]), row["payload_sha256"]
            )
        runner.validate_request_bundle(bundle, self.config)

    def test_offline_preflight_records_provider_limits_without_fake_tokens(self):
        preflight = self.built["preflight"]
        self.assertTrue(preflight["all_offline_preflight_checks_passed"])
        self.assertEqual(
            preflight["provider_constraints_snapshot"]["max_function_count"], 128
        )
        self.assertEqual(
            preflight["provider_constraints_snapshot"]["context_length_tokens"],
            1_000_000,
        )
        for row in preflight["rows"]:
            self.assertTrue(row["function_count_within_documented_limit"])
            self.assertIsNone(row["provider_exact_schema_token_count"])
            self.assertGreater(row["schema_utf8_byte_count"], 0)

    def test_policy_and_design_mutations_are_rejected(self):
        for field in (
            "tool_execution_allowed",
            "fallback_tool_count_reduction_allowed",
            "text_catalog_fallback_allowed",
            "external_api_calls_authorized",
            "confirmatory_inference_allowed",
            "core_frozen",
        ):
            invalid = copy.deepcopy(self.config)
            invalid[field] = True
            with self.assertRaisesRegex(ValueError, "must remain false"):
                builder.build(invalid, self.prompts)
        invalid = copy.deepcopy(self.config)
        invalid["provider_max_attempts"] = 2
        with self.assertRaisesRegex(ValueError, "must not be silently retried"):
            builder.build(invalid, self.prompts)

    def test_fake_execution_sends_exactly_ten_requests_without_tool_execution(self):
        adapter = FakeAdapter(self.config)
        executed = runner.execute(
            self.built["request_bundle"],
            self.config,
            adapter,
        )
        report = executed["report"]
        self.assertEqual(len(adapter.calls), 10)
        self.assertEqual(report["external_api_calls"], 10)
        self.assertTrue(report["all_baselines_accepted"])
        self.assertTrue(report["all_full_schema_probes_accepted"])
        self.assertTrue(report["tool_choice_none_enforced_all_sizes"])
        self.assertTrue(report["provider_token_deltas_available_all_sizes"])
        self.assertEqual(report["tool_calls_executed"], 0)
        self.assertEqual(report["fallbacks_applied"], 0)
        for row in executed["results"]:
            self.assertFalse(row["tool_executed"])
            self.assertFalse(row["fallback_applied"])

    def test_pending_request_cannot_authorize_runner(self):
        with workspace_test_directory() as temp_dir:
            output_dir = temp_dir / "opening"
            builder.build_outputs(output_dir)
            pending = builder.load_json(output_dir / "execution_authorization_request.json")
            with self.assertRaisesRegex(ValueError, "mismatch for decision"):
                runner.validate_authorization(
                    pending,
                    output_dir / "cf06_request_bundle.json",
                    output_dir,
                    self.config,
                )

    def test_hash_bound_authorization_is_accepted_but_tampering_is_rejected(self):
        with workspace_test_directory() as temp_dir:
            output_dir = temp_dir / "opening"
            builder.build_outputs(output_dir)
            request = builder.load_json(output_dir / "execution_authorization_request.json")
            authorization = {
                **request,
                "decision": "authorized_to_execute_cf06_feasibility",
                "external_data_sharing_authorized": True,
                "external_api_execution_authorized": True,
                "authorized_by": "unit-test",
                "authorized_at": datetime.now(timezone.utc).isoformat(),
            }
            runner.validate_authorization(
                authorization,
                output_dir / "cf06_request_bundle.json",
                output_dir,
                self.config,
            )
            tampered = copy.deepcopy(authorization)
            tampered["request_bundle_sha256"] = "0" * 64
            with self.assertRaisesRegex(
                ValueError, "mismatch for request_bundle_sha256"
            ):
                runner.validate_authorization(
                    tampered,
                    output_dir / "cf06_request_bundle.json",
                    output_dir,
                    self.config,
                )

    def test_fake_end_to_end_runner_writes_hash_complete_evidence(self):
        with workspace_test_directory() as temp_dir:
            opening_dir = temp_dir / "opening"
            runtime_dir = temp_dir / "runtime"
            builder.build_outputs(opening_dir)
            request = builder.load_json(
                opening_dir / "execution_authorization_request.json"
            )
            authorization = {
                **request,
                "decision": "authorized_to_execute_cf06_feasibility",
                "external_data_sharing_authorized": True,
                "external_api_execution_authorized": True,
                "authorized_by": "unit-test",
                "authorized_at": datetime.now(timezone.utc).isoformat(),
            }
            authorization_path = temp_dir / "authorization.json"
            builder.write_json(authorization_path, authorization)
            report = runner.build_outputs(
                bundle_path=opening_dir / "cf06_request_bundle.json",
                authorization_path=authorization_path,
                output_dir=runtime_dir,
                adapter=FakeAdapter(self.config),
            )
            self.assertEqual(
                report["run_status"], "runtime_feasible_candidate_pending_review"
            )
            self.assertEqual(report["tool_calls_executed"], 0)
            manifest = runner.load_json(runtime_dir / "artifact_manifest.json")
            self.assertEqual(manifest["artifact_count"], 7)
            for row in manifest["artifacts"]:
                path = runtime_dir / row["filename"]
                self.assertEqual(runner.file_hash(path), row["sha256"])
                self.assertEqual(path.stat().st_size, row["bytes"])

    def test_fresh_opening_has_complete_artifact_manifest(self):
        with workspace_test_directory() as temp_dir:
            output_dir = temp_dir / "opening"
            report = builder.build_outputs(output_dir)
            self.assertEqual(report["external_api_calls"], 0)
            self.assertFalse(report["external_api_execution_authorized"])
            manifest = builder.load_json(output_dir / "artifact_manifest.json")
            self.assertEqual(manifest["artifact_count"], 9)
            for row in manifest["artifacts"]:
                path = output_dir / row["filename"]
                self.assertEqual(builder.file_hash(path), row["sha256"])
                self.assertEqual(path.stat().st_size, row["bytes"])


if __name__ == "__main__":
    unittest.main()
