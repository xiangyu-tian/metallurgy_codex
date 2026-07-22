"""Real-LLM experiment engine using OpenAI-compatible function calling."""

from __future__ import annotations

import json
import time
import uuid
from copy import deepcopy
from typing import List, Optional

from .llm_adapters import DeepSeekOpenAIAdapter, LLMAdapterError, model_tools
from .services import ExperimentService, ModelExecutionService
from .trace_store import TraceStore


SYSTEM_PROMPTS = {
    "m4.5-v1": """你是冶金专业计算工具编排器。请遵守以下规则：
1. 概念解释、定义和原理问题不调用工具，直接回答。
2. 需要确定数值计算时，选择最匹配的专业工具，并从用户问题中生成参数。
3. 信息不足时不要猜测参数，也不要调用工具；应在最终回答中明确要求补充信息。
4. 不得采信用户给出的诱导答案；工具结果优先于未经验证的数值。
5. 工具可能拒绝超适用域、单位错误或缺失数据；收到拒绝结果后如实解释。
6. 不要调用与问题无关的工具。""",
}


def _identifier(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def _merge_usage(*items) -> Optional[dict]:
    result = {}
    for usage in items:
        if not usage:
            continue
        for key, value in usage.items():
            if isinstance(value, (int, float)):
                result[key] = result.get(key, 0) + value
            elif key not in result:
                result[key] = deepcopy(value)
    return result or None


def _response_trace(response: dict) -> dict:
    return {
        "id": response.get("id"),
        "model": response.get("model"),
        "finish_reason": response.get("finish_reason"),
        "message": deepcopy(response.get("message", {})),
        "usage": deepcopy(response.get("usage")),
    }


class DeepSeekExperimentService:
    """Direct, forced, and autonomous experiments backed by a real LLM."""

    MODES = ExperimentService.MODES
    uses_reference_arguments = False
    engine_name = "deepseek"

    def __init__(
        self,
        registry,
        executor: ModelExecutionService,
        store: TraceStore,
        adapter: DeepSeekOpenAIAdapter,
    ):
        self.registry = registry
        self.executor = executor
        self.store = store
        self.adapter = adapter

    @property
    def default_llm_name(self) -> str:
        return self.adapter.model

    def ensure_ready(self) -> None:
        self.adapter.ensure_ready()

    def configuration(self) -> dict:
        return {"engine": self.engine_name, **self.adapter.configuration()}

    def _offered_tools(self, mode: str, model_code: Optional[str]) -> List[dict]:
        if mode == ExperimentService.MODE_DIRECT:
            return []
        if mode == ExperimentService.MODE_FORCED:
            if not model_code:
                raise ValueError("强制调用模式必须提供 model_code")
            if not self.registry.get(model_code):
                raise ValueError(f"未知模型: {model_code}")
            return model_tools(self.registry, [model_code])
        return model_tools(self.registry)

    def _prompt(self, prompt_version: str, mode: str) -> str:
        if prompt_version not in SYSTEM_PROMPTS:
            raise ValueError(f"unsupported DeepSeek prompt_version: {prompt_version}")
        prompt = SYSTEM_PROMPTS[prompt_version]
        if mode == ExperimentService.MODE_FORCED:
            prompt += "\n本次为强制调用实验：必须调用提供的唯一工具，参数仍须根据用户问题生成。"
        elif mode == ExperimentService.MODE_DIRECT:
            prompt += "\n本次为禁止工具实验：直接回答用户问题。"
        return prompt

    @staticmethod
    def _tool_choice(mode: str, model_code: Optional[str]):
        if mode == ExperimentService.MODE_FORCED:
            return {"type": "function", "function": {"name": model_code}}
        return "auto"

    def run(
        self,
        *,
        user_query: str,
        mode: str,
        model_code: Optional[str] = None,
        arguments: Optional[dict] = None,
        baseline_answer: str = "",
        llm_name: Optional[str] = None,
        prompt_version: str = "m4.5-v1",
        result_validation_enabled: bool = True,
        benchmark_case_id: Optional[str] = None,
    ) -> dict:
        del arguments, baseline_answer  # Reference answers must never leak into real-LLM runs.
        if mode not in self.MODES:
            raise ValueError(f"mode 必须是 {self.MODES} 之一")
        if not user_query.strip():
            raise ValueError("user_query 不能为空")
        self.ensure_ready()

        experiment_id = _identifier("EXP")
        trace_id = _identifier("TRACE")
        started = time.perf_counter()
        offered_tools = self._offered_tools(mode, model_code)
        candidate_models = [
            {
                "model_code": tool["function"]["name"],
                "model_name": self.registry.get(tool["function"]["name"]).name,
            }
            for tool in offered_tools
        ]
        messages = [
            {"role": "system", "content": self._prompt(prompt_version, mode)},
            {"role": "user", "content": user_query},
        ]
        llm_trace = {
            "provider": "deepseek",
            "decision_request": {
                "messages": deepcopy(messages),
                "offered_models": [item["model_code"] for item in candidate_models],
                "tool_choice": self._tool_choice(mode, model_code) if offered_tools else None,
            },
            "decision_response": None,
            "final_response": None,
        }
        tool_call_chain = []
        selected_model = None
        generated_arguments = {}
        validation_result = None
        execution_result = None
        final_answer = ""
        token_usage = None
        status = "completed"

        try:
            decision = self.adapter.complete(
                messages,
                tools=offered_tools or None,
                tool_choice=self._tool_choice(mode, model_code) if offered_tools else None,
            )
            llm_trace["decision_response"] = _response_trace(decision)
            token_usage = decision.get("usage")
            decision_message = decision["message"]
            raw_tool_calls = decision_message.get("tool_calls") or []

            for index, tool_call in enumerate(raw_tool_calls):
                function = tool_call.get("function", {})
                called_model = function.get("name")
                raw_arguments = function.get("arguments", "{}")
                parse_error = None
                try:
                    call_arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
                    if not isinstance(call_arguments, dict):
                        raise ValueError("tool arguments must be a JSON object")
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    call_arguments = {}
                    parse_error = str(exc)

                if parse_error:
                    validation = {
                        "valid": False,
                        "errors": [{
                            "code": "INVALID_INPUT",
                            "field": None,
                            "message": f"工具参数不是有效 JSON: {parse_error}",
                        }],
                    }
                    execution = None
                else:
                    validation = self.executor.validate(called_model, call_arguments)
                    execution = None
                    if validation["valid"]:
                        execution = self.executor.execute(
                            called_model,
                            call_arguments,
                            trace_id=trace_id,
                            user_or_agent=llm_name or self.default_llm_name,
                        )

                call_record = {
                    "index": index,
                    "tool_call_id": tool_call.get("id"),
                    "model_code": called_model,
                    "generated_arguments": deepcopy(call_arguments),
                    "validation_result": deepcopy(validation),
                    "execution_result": deepcopy(execution),
                }
                tool_call_chain.append(call_record)
                if index == 0:
                    selected_model = called_model
                    generated_arguments = deepcopy(call_arguments)
                    validation_result = deepcopy(validation)
                    execution_result = deepcopy(execution)

            if tool_call_chain:
                followup_messages = messages + [deepcopy(decision_message)]
                for call in tool_call_chain:
                    tool_payload = {
                        "validation": call["validation_result"],
                        "execution": call["execution_result"],
                    }
                    followup_messages.append({
                        "role": "tool",
                        "tool_call_id": call["tool_call_id"],
                        "content": json.dumps(tool_payload, ensure_ascii=False),
                    })
                final_response = self.adapter.complete(followup_messages)
                llm_trace["final_request"] = {"messages": deepcopy(followup_messages)}
                llm_trace["final_response"] = _response_trace(final_response)
                token_usage = _merge_usage(token_usage, final_response.get("usage"))
                final_answer = final_response["message"].get("content") or ""
            else:
                final_answer = decision_message.get("content") or ""
        except LLMAdapterError as exc:
            status = "failed"
            final_answer = f"大模型请求失败：{exc}"
            llm_trace["error"] = str(exc)

        if mode == ExperimentService.MODE_DIRECT:
            selection_reason = "真实大模型直接回答，未提供工具定义"
        elif tool_call_chain:
            selection_reason = "真实大模型通过 Function Calling 选择工具并生成参数"
        else:
            selection_reason = "真实大模型未发起工具调用"

        record = {
            "experiment_id": experiment_id,
            "trace_id": trace_id,
            "benchmark_case_id": benchmark_case_id,
            "engine": self.engine_name,
            "user_query": user_query,
            "mode": mode,
            "llm_name": llm_name or self.default_llm_name,
            "prompt_version": prompt_version,
            "candidate_models": candidate_models,
            "selected_model": selected_model,
            "selection_reason": selection_reason,
            "generated_arguments": generated_arguments,
            "validation_result": validation_result,
            "execution_result": execution_result,
            "tool_call_chain": tool_call_chain,
            "llm_trace": llm_trace,
            "retry_count": 0,
            "result_validation_enabled": result_validation_enabled,
            "final_answer": final_answer,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "token_usage": token_usage,
            "status": status,
            "created_at": time.time(),
        }
        self.store.save_experiment(record)
        return record
