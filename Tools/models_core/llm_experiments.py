"""Real-LLM experiment engine using OpenAI-compatible function calling."""

from __future__ import annotations

import json
import time
import uuid
from copy import deepcopy
from typing import List, Optional

from .candidate_retrieval import CandidateModelRetriever
from .llm_adapters import DeepSeekOpenAIAdapter, LLMAdapterError, model_tools
from .services import ExperimentService, ModelExecutionService
from .trace_store import TraceStore


_BASE_SYSTEM_PROMPT = """你是冶金专业计算工具编排器。请遵守以下规则：
1. 概念解释、定义和原理问题不调用工具，直接回答。
2. 需要确定数值计算时，选择最匹配的专业工具，并从用户问题中生成参数。
3. 信息不足时不要猜测参数，也不要调用工具；应在最终回答中明确要求补充信息。
4. 不得采信用户给出的诱导答案；工具结果优先于未经验证的数值。
5. 工具可能拒绝超适用域、单位错误或缺失数据；收到拒绝结果后如实解释。
6. 不要调用与问题无关的工具。"""

_MULTI_ROUND_SYSTEM_PROMPT = _BASE_SYSTEM_PROMPT + """
7. 多步任务中，如果后续工具参数依赖前一步结果，只调用当前参数已确定的工具；收到结果后再决定下一步。
8. 已有结果足以回答时立即停止调用；禁止用完全相同的参数重复调用同一工具。"""

SYSTEM_PROMPTS = {
    "m4.5-v1": _BASE_SYSTEM_PROMPT,
    "m4.6-v1": _MULTI_ROUND_SYSTEM_PROMPT,
    "m4.6b-v1": _MULTI_ROUND_SYSTEM_PROMPT,
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
    default_prompt_version = "m4.6b-v1"
    multi_round_prompt_versions = frozenset({"m4.6-v1", "m4.6b-v1"})
    retrieval_prompt_versions = frozenset({"m4.6b-v1"})

    def __init__(
        self,
        registry,
        executor: ModelExecutionService,
        store: TraceStore,
        adapter: DeepSeekOpenAIAdapter,
        *,
        max_tool_rounds: int = 3,
        max_tool_calls: int = 5,
        candidate_top_k: int = 5,
        candidate_retriever=None,
    ):
        if max_tool_rounds < 1:
            raise ValueError("max_tool_rounds 必须大于等于 1")
        if max_tool_calls < 1:
            raise ValueError("max_tool_calls 必须大于等于 1")
        if candidate_top_k < 1:
            raise ValueError("candidate_top_k 必须大于等于 1")
        self.registry = registry
        self.executor = executor
        self.store = store
        self.adapter = adapter
        self.max_tool_rounds = max_tool_rounds
        self.max_tool_calls = max_tool_calls
        self.candidate_top_k = candidate_top_k
        self.candidate_retriever = (
            candidate_retriever or CandidateModelRetriever(registry)
        )

    @property
    def default_llm_name(self) -> str:
        return self.adapter.model

    def ensure_ready(self) -> None:
        self.adapter.ensure_ready()

    def configuration(self) -> dict:
        return {
            "engine": self.engine_name,
            "default_prompt_version": self.default_prompt_version,
            "max_tool_rounds": self.max_tool_rounds,
            "max_tool_calls": self.max_tool_calls,
            "candidate_retrieval_strategy": self.candidate_retriever.strategy,
            "candidate_top_k": self.candidate_top_k,
            "retrieval_prompt_versions": sorted(self.retrieval_prompt_versions),
            **self.adapter.configuration(),
        }

    def _offered_tools(
        self,
        mode: str,
        model_code: Optional[str],
        user_query: str,
        prompt_version: str,
    ) -> tuple[List[dict], dict]:
        if mode == ExperimentService.MODE_DIRECT:
            return [], {
                "strategy": "disabled-direct",
                "top_k": 0,
                "candidate_models": [],
                "fallback_used": False,
                "fallback_reason": "direct_mode",
            }
        if mode == ExperimentService.MODE_FORCED:
            if not model_code:
                raise ValueError("强制调用模式必须提供 model_code")
            model = self.registry.get(model_code)
            if not model:
                raise ValueError(f"未知模型: {model_code}")
            candidates = [{
                "rank": 1,
                "model_code": model_code,
                "model_name": model.name,
                "score": None,
                "matched_terms": [],
                "reason": "强制调用实验指定模型",
            }]
            return model_tools(self.registry, [model_code]), {
                "strategy": "forced-model-control",
                "top_k": 1,
                "candidate_models": candidates,
                "fallback_used": False,
                "fallback_reason": None,
            }
        if prompt_version in self.retrieval_prompt_versions:
            retrieval = self.candidate_retriever.retrieve(
                user_query,
                top_k=self.candidate_top_k,
            )
            model_codes = [
                item["model_code"]
                for item in retrieval["candidate_models"]
            ]
            return model_tools(self.registry, model_codes), retrieval

        tools = model_tools(self.registry)
        candidates = [{
            "rank": rank,
            "model_code": tool["function"]["name"],
            "model_name": self.registry.get(tool["function"]["name"]).name,
            "score": None,
            "matched_terms": [],
            "reason": "M4.6 全量工具对照",
        } for rank, tool in enumerate(tools, start=1)]
        return tools, {
            "strategy": "all-models-control",
            "top_k": len(candidates),
            "candidate_models": candidates,
            "fallback_used": False,
            "fallback_reason": None,
        }

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

    @staticmethod
    def _tool_signature(model_code: Optional[str], arguments, raw_arguments) -> str:
        if isinstance(arguments, dict):
            normalized = json.dumps(
                arguments,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        else:
            normalized = f"RAW:{raw_arguments}"
        return f"{model_code}:{normalized}"

    def _execute_tool_call(
        self,
        tool_call: dict,
        *,
        trace_id: str,
        llm_name: str,
        round_number: int,
        round_index: int,
        global_index: int,
        seen_signatures: set,
    ) -> dict:
        function = tool_call.get("function", {})
        called_model = function.get("name")
        raw_arguments = function.get("arguments", "{}")
        parse_error = None
        parsed_arguments = None
        try:
            parsed_arguments = (
                json.loads(raw_arguments)
                if isinstance(raw_arguments, str)
                else raw_arguments
            )
            if not isinstance(parsed_arguments, dict):
                raise ValueError("tool arguments must be a JSON object")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            call_arguments = {}
            parse_error = str(exc)
        else:
            call_arguments = parsed_arguments

        signature = self._tool_signature(
            called_model,
            parsed_arguments,
            raw_arguments,
        )
        duplicate = signature in seen_signatures
        seen_signatures.add(signature)

        if duplicate:
            validation = {
                "valid": False,
                "errors": [{
                    "code": "DUPLICATE_TOOL_CALL",
                    "field": None,
                    "message": "同一工具及参数已经调用过，终止重复调用",
                }],
            }
            execution = None
        elif parse_error:
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
                    user_or_agent=llm_name,
                )

        return {
            "index": global_index,
            "round": round_number,
            "round_index": round_index,
            "tool_call_id": tool_call.get("id"),
            "model_code": called_model,
            "generated_arguments": deepcopy(call_arguments),
            "signature": signature,
            "duplicate": duplicate,
            "validation_result": deepcopy(validation),
            "execution_result": deepcopy(execution),
        }

    def run(
        self,
        *,
        user_query: str,
        mode: str,
        model_code: Optional[str] = None,
        arguments: Optional[dict] = None,
        baseline_answer: str = "",
        llm_name: Optional[str] = None,
        prompt_version: str = "m4.6b-v1",
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
        offered_tools, retrieval = self._offered_tools(
            mode,
            model_code,
            user_query,
            prompt_version,
        )
        effective_llm_name = llm_name or self.default_llm_name
        multi_round_enabled = (
            mode == ExperimentService.MODE_AUTONOMOUS
            and prompt_version in self.multi_round_prompt_versions
        )
        retrieval_enabled = (
            mode == ExperimentService.MODE_AUTONOMOUS
            and prompt_version in self.retrieval_prompt_versions
        )
        candidate_models = deepcopy(retrieval["candidate_models"])
        messages = [
            {"role": "system", "content": self._prompt(prompt_version, mode)},
            {"role": "user", "content": user_query},
        ]
        llm_trace = {
            "provider": "deepseek",
            "policy": {
                "multi_round_enabled": multi_round_enabled,
                "retrieval_enabled": retrieval_enabled,
                "max_tool_rounds": self.max_tool_rounds,
                "max_tool_calls": self.max_tool_calls,
                "candidate_top_k": self.candidate_top_k,
            },
            "retrieval": deepcopy(retrieval),
            "decision_request": {
                "messages": deepcopy(messages),
                "offered_models": [item["model_code"] for item in candidate_models],
                "tool_choice": self._tool_choice(mode, model_code) if offered_tools else None,
            },
            "decision_response": None,
            "final_response": None,
            "rounds": [],
        }
        tool_call_chain = []
        seen_signatures = set()
        selected_model = None
        generated_arguments = {}
        validation_result = None
        execution_result = None
        final_answer = ""
        token_usage = None
        status = "completed"
        tool_round_count = 0
        stop_reason = None

        try:
            while True:
                tool_choice = (
                    self._tool_choice(mode, model_code)
                    if offered_tools
                    else None
                )
                request_kwargs = {"tools": offered_tools or None}
                if offered_tools:
                    request_kwargs["tool_choice"] = tool_choice
                decision = self.adapter.complete(messages, **request_kwargs)
                response_round = len(llm_trace["rounds"]) + 1
                response_trace = _response_trace(decision)
                if llm_trace["decision_response"] is None:
                    llm_trace["decision_response"] = deepcopy(response_trace)
                token_usage = _merge_usage(token_usage, decision.get("usage"))
                decision_message = decision["message"]
                raw_tool_calls = decision_message.get("tool_calls") or []
                round_trace = {
                    "round": response_round,
                    "request": {
                        "messages": deepcopy(messages),
                        "offered_models": [
                            item["model_code"] for item in candidate_models
                        ],
                        "tool_choice": deepcopy(tool_choice),
                    },
                    "response": response_trace,
                    "received_tool_call_count": len(raw_tool_calls),
                    "processed_tool_call_count": 0,
                }
                llm_trace["rounds"].append(round_trace)

                if not raw_tool_calls or not offered_tools:
                    final_answer = decision_message.get("content") or ""
                    llm_trace["final_response"] = deepcopy(response_trace)
                    stop_reason = "assistant_final"
                    break

                tool_round_count += 1
                remaining_calls = self.max_tool_calls - len(tool_call_chain)
                calls_to_process = raw_tool_calls[:remaining_calls]
                processed_tool_calls = []
                processed_records = []
                duplicate_found = False
                for round_index, tool_call in enumerate(calls_to_process):
                    call_record = self._execute_tool_call(
                        tool_call,
                        trace_id=trace_id,
                        llm_name=effective_llm_name,
                        round_number=tool_round_count,
                        round_index=round_index,
                        global_index=len(tool_call_chain),
                        seen_signatures=seen_signatures,
                    )
                    tool_call_chain.append(call_record)
                    processed_tool_calls.append(deepcopy(tool_call))
                    processed_records.append(call_record)
                    if selected_model is None:
                        selected_model = call_record["model_code"]
                        generated_arguments = deepcopy(
                            call_record["generated_arguments"]
                        )
                        validation_result = deepcopy(
                            call_record["validation_result"]
                        )
                        execution_result = deepcopy(
                            call_record["execution_result"]
                        )
                    if call_record["duplicate"]:
                        duplicate_found = True
                        break

                round_trace["processed_tool_call_count"] = len(processed_records)
                normalized_message = deepcopy(decision_message)
                normalized_message["tool_calls"] = processed_tool_calls
                messages.append(normalized_message)
                for call in processed_records:
                    tool_payload = {
                        "validation": call["validation_result"],
                        "execution": call["execution_result"],
                    }
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call["tool_call_id"],
                        "content": json.dumps(tool_payload, ensure_ascii=False),
                    })

                if duplicate_found:
                    stop_reason = "duplicate_tool_call"
                    break
                if len(tool_call_chain) >= self.max_tool_calls:
                    stop_reason = "tool_call_limit"
                    break
                if not multi_round_enabled:
                    stop_reason = (
                        "forced_single_round"
                        if mode == ExperimentService.MODE_FORCED
                        else "single_round_policy"
                    )
                    break
                if tool_round_count >= self.max_tool_rounds:
                    stop_reason = "tool_round_limit"
                    break

            if stop_reason != "assistant_final":
                synthesis_messages = messages + [{
                    "role": "system",
                    "content": (
                        "工具调用阶段已经结束。请仅根据已有工具结果生成最终回答，"
                        "不要再请求调用工具；若结果不足，请明确说明限制。"
                    ),
                }]
                final_response = self.adapter.complete(synthesis_messages)
                llm_trace["final_request"] = {
                    "messages": deepcopy(synthesis_messages),
                }
                llm_trace["final_response"] = _response_trace(final_response)
                token_usage = _merge_usage(
                    token_usage,
                    final_response.get("usage"),
                )
                final_answer = final_response["message"].get("content") or ""
        except LLMAdapterError as exc:
            status = "failed"
            final_answer = f"大模型请求失败：{exc}"
            llm_trace["error"] = str(exc)
            stop_reason = "provider_error"

        llm_trace["tool_round_count"] = tool_round_count
        llm_trace["stop_reason"] = stop_reason

        if mode == ExperimentService.MODE_DIRECT:
            selection_reason = "真实大模型直接回答，未提供工具定义"
        elif tool_call_chain:
            selection_reason = (
                "候选召回后由真实大模型通过 Function Calling 选择工具并生成参数"
                if retrieval_enabled
                else "真实大模型通过 Function Calling 选择工具并生成参数"
            )
        else:
            selection_reason = "真实大模型未发起工具调用"

        record = {
            "experiment_id": experiment_id,
            "trace_id": trace_id,
            "benchmark_case_id": benchmark_case_id,
            "engine": self.engine_name,
            "user_query": user_query,
            "mode": mode,
            "llm_name": effective_llm_name,
            "prompt_version": prompt_version,
            "candidate_models": candidate_models,
            "candidate_retrieval": deepcopy(retrieval),
            "selected_model": selected_model,
            "selection_reason": selection_reason,
            "generated_arguments": generated_arguments,
            "validation_result": validation_result,
            "execution_result": execution_result,
            "tool_call_chain": tool_call_chain,
            "llm_trace": llm_trace,
            "tool_round_count": tool_round_count,
            "retry_count": max(0, tool_round_count - 1),
            "stop_reason": stop_reason,
            "result_validation_enabled": result_validation_enabled,
            "final_answer": final_answer,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "token_usage": token_usage,
            "status": status,
            "created_at": time.time(),
        }
        self.store.save_experiment(record)
        return record
