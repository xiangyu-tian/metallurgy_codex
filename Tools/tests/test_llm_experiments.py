"""Offline contract tests for the real-LLM M4.5 experiment engine."""

import os
import sys
import unittest
import json


TOOLS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, TOOLS_DIR)

from models_core import ModelRegistry
from models_core.llm_adapters import DeepSeekOpenAIAdapter, model_tools
from models_core.llm_experiments import DeepSeekExperimentService
from models_core.benchmarking import BenchmarkService, ToolCallingDataset
from models_core.services import ModelExecutionService
from models_core.trace_store import InMemoryTraceStore


def response(message, *, response_id="chat-1", usage=None, finish_reason="stop"):
    return {
        "id": response_id,
        "model": "deepseek-v4-flash",
        "message": message,
        "finish_reason": finish_reason,
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


class FakeAdapter:
    model = "deepseek-v4-flash"

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def ensure_ready(self):
        return None

    def configuration(self):
        return {"provider": "deepseek", "model": self.model, "api_key_configured": True}

    def complete(self, messages, **kwargs):
        self.requests.append({"messages": messages, **kwargs})
        return self.responses.pop(0)


class DeepSeekAdapterContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ModelRegistry()
        cls.registry.discover()

    def test_all_frozen_model_cards_convert_to_function_tools(self):
        tools = model_tools(self.registry)
        self.assertEqual(len(tools), 17)
        self.assertEqual({tool["function"]["name"] for tool in tools}, {
            card["model_code"] for card in self.registry.list_models()
        })
        a005 = next(tool for tool in tools if tool["function"]["name"] == "A005")
        properties = a005["function"]["parameters"]["properties"]
        self.assertEqual(properties["input_streams"]["type"], "array")
        self.assertEqual(properties["output_streams"]["items"]["type"], "object")
        valid_types = {"string", "number", "integer", "boolean", "object", "array", "null"}

        def assert_schema_types(schema):
            self.assertIn(schema["type"], valid_types)
            for child in schema.get("properties", {}).values():
                assert_schema_types(child)
            if isinstance(schema.get("items"), dict):
                assert_schema_types(schema["items"])

        for tool in tools:
            assert_schema_types(tool["function"]["parameters"])

    def test_provider_failure_cannot_pass_a_no_tool_case(self):
        case = ToolCallingDataset().get("TC-NO_TOOL-001")
        metrics = BenchmarkService.evaluate(case, {
            "status": "failed",
            "selected_model": None,
            "tool_call_chain": [],
            "generated_arguments": {},
            "validation_result": None,
            "execution_result": None,
        })

        self.assertFalse(metrics["experiment_completed"])
        self.assertFalse(metrics["tool_decision_correct"])
        self.assertFalse(metrics["outcome_correct"])
        self.assertFalse(metrics["case_passed"])

    def test_adapter_builds_openai_request_without_exposing_key_in_configuration(self):
        captured = {}

        def transport(url, headers, payload, timeout):
            captured.update(url=url, headers=headers, payload=payload, timeout=timeout)
            return {
                "id": "chat-test",
                "model": "deepseek-v4-flash",
                "choices": [{
                    "message": {"role": "assistant", "content": "CONNECTED"},
                    "finish_reason": "stop",
                }],
                "usage": {"total_tokens": 4},
            }

        adapter = DeepSeekOpenAIAdapter(
            api_key="test-secret",
            base_url="https://provider.example/",
            transport=transport,
        )
        result = adapter.complete([{"role": "user", "content": "ping"}])

        self.assertEqual(captured["url"], "https://provider.example/chat/completions")
        self.assertEqual(captured["payload"]["thinking"], {"type": "disabled"})
        self.assertEqual(result["message"]["content"], "CONNECTED")
        self.assertNotIn("api_key", adapter.configuration())


class DeepSeekExperimentServiceTests(unittest.TestCase):
    def setUp(self):
        self.registry = ModelRegistry()
        self.registry.discover()
        self.store = InMemoryTraceStore()
        self.executor = ModelExecutionService(self.registry, self.store)

    def test_forced_mode_uses_llm_generated_arguments_executes_and_returns_result(self):
        adapter = FakeAdapter([
            response({
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "A003", "arguments": '{"formula":"Fe2O3"}'},
                }],
            }, finish_reason="tool_calls"),
            response(
                {"role": "assistant", "content": "Fe2O3 的摩尔质量约为 159.687 g/mol。"},
                response_id="chat-2",
                usage={"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
            ),
        ])
        service = DeepSeekExperimentService(
            self.registry, self.executor, self.store, adapter
        )

        record = service.run(
            user_query="计算 Fe2O3 的摩尔质量",
            mode="forced",
            model_code="A003",
            arguments={"formula": "REFERENCE_MUST_BE_IGNORED"},
        )

        self.assertEqual(record["engine"], "deepseek")
        self.assertEqual(record["generated_arguments"], {"formula": "Fe2O3"})
        self.assertEqual(record["execution_result"]["status"], "success")
        self.assertEqual(len(record["tool_call_chain"]), 1)
        self.assertEqual(record["token_usage"]["total_tokens"], 43)
        self.assertIn("159.687", record["final_answer"])
        self.assertEqual(len(adapter.requests), 2)
        self.assertEqual(adapter.requests[0]["tool_choice"]["function"]["name"], "A003")
        self.assertNotIn("tools", adapter.requests[1])

    def test_direct_mode_does_not_offer_tools(self):
        adapter = FakeAdapter([
            response({"role": "assistant", "content": "Shomate 方程用于表示热容。"}),
        ])
        service = DeepSeekExperimentService(
            self.registry, self.executor, self.store, adapter
        )

        record = service.run(user_query="什么是 Shomate 方程？", mode="direct")

        self.assertIsNone(record["selected_model"])
        self.assertEqual(record["tool_call_chain"], [])
        self.assertIsNone(adapter.requests[0]["tools"])
        self.assertIn("Shomate", record["final_answer"])

    def test_benchmark_routes_same_case_to_deepseek_without_reference_argument_leak(self):
        dataset = ToolCallingDataset()
        case = dataset.get("TC-SINGLE_TOOL-001")
        adapter = FakeAdapter([
            response({
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "call-benchmark",
                    "type": "function",
                    "function": {
                        "name": case["forced_model_code"],
                        "arguments": json.dumps(case["standard_arguments"], ensure_ascii=False),
                    },
                }],
            }, finish_reason="tool_calls"),
            response({"role": "assistant", "content": "计算完成。"}, response_id="chat-final"),
        ])
        real_service = DeepSeekExperimentService(
            self.registry, self.executor, self.store, adapter
        )
        deterministic = object()
        benchmark = BenchmarkService(
            dataset,
            deterministic,
            self.store,
            experiment_engines={"deepseek": real_service},
        )

        result = benchmark.run(
            engine="deepseek",
            modes=["forced"],
            case_ids=[case["case_id"]],
            max_cases=1,
        )

        self.assertEqual(result["configuration"]["engine"], "deepseek")
        self.assertEqual(result["configuration"]["llm_name"], "deepseek-v4-flash")
        self.assertEqual(result["total_experiments"], 1)
        self.assertTrue(result["results"][0]["metrics"]["arguments_exact_match"])
        decision_messages = adapter.requests[0]["messages"]
        self.assertNotIn("standard_arguments", json.dumps(decision_messages, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
