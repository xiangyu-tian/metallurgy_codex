"""Tool-calling benchmark dataset access and deterministic batch evaluation."""

from __future__ import annotations

import json
import math
import os
import re
import time
import uuid
from collections import Counter
from copy import deepcopy
from typing import Dict, Iterable, List, Optional

from .services import ExperimentService
from .trace_store import TraceStore


REQUIRED_CATEGORIES = {
    "no_tool", "single_tool", "multi_tool", "insufficient_info",
    "out_of_domain", "adversarial",
}
EVALUATOR_VERSION = "1.1.2"

_NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.])[-+]?(?:\d+(?:,\d{3})*(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
)
_SCIENTIFIC_PATTERN = re.compile(
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:×|x|\*|\\times)\s*"
    r"10\s*(?:\^|\*\*)?\s*\{?\s*([-+]?\d+)\s*\}?",
    re.IGNORECASE,
)
_PERCENT_PATTERN = re.compile(r"([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*[%％]")
_FRACTION_PATTERN = re.compile(r"(?<![\d.])([-+]?\d+)\s*/\s*(\d+)(?![\d.])")
_SUPERSCRIPT_TRANSLATION = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")
_DOMAIN_REJECTION_MARKERS = (
    "维度不一致", "量纲不一致", "物理量纲", "无效输入", "无效化学式",
    "错误化学式", "未知物种", "不是一个已知", "不是已知", "超出适用",
    "超出范围", "不在其适用域", "不守恒", "不适用", "失效",
)
_CLARIFICATION_MARKERS = (
    "请提供", "请补充", "需要您补充", "需要提供", "您没有提供",
    "由于您未提供", "如果您能提供", "缺少必要", "请明确", "需要具体",
    "需要先明确", "信息不足", "无法确定", "还需要", "想计算哪个",
)
_OPENING_REJECTION_MARKERS = (
    "无法换算", "无法执行", "无法将", "无法解析", "不能换算", "不能直接",
    "不可计算", "不能计算",
)


def _identifier(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def _value_at_path(payload, path: str):
    value = payload
    for part in path.split("."):
        value = value[part]
    return value


def _final_behavior(experiment: dict) -> str:
    if experiment.get("status", "completed") != "completed":
        return "provider_failure"
    chain = experiment.get("tool_call_chain") or []
    if chain:
        rejected = any(
            not (item.get("validation_result") or {}).get("valid", False)
            or (item.get("execution_result") or {}).get("status") in {"rejected", "error"}
            for item in chain
        )
        if rejected:
            return "tool_reject"
        succeeded = all(
            (item.get("execution_result") or {}).get("status") == "success"
            for item in chain
        )
        if succeeded:
            return "multi_tool_success" if len(chain) > 1 else "tool_success"
        return "tool_failed"

    answer = (experiment.get("final_answer") or "").strip()
    opening = answer.split("\n\n", 1)[0]
    if any(marker in answer for marker in _DOMAIN_REJECTION_MARKERS):
        return "direct_reject"
    if any(marker in answer for marker in _CLARIFICATION_MARKERS):
        return "clarify"
    if any(marker in opening for marker in _OPENING_REJECTION_MARKERS):
        return "direct_reject"
    return "direct_answer" if answer else "empty_answer"


def _numeric_answer_correct(answer: str, case: dict) -> bool:
    expected_result = case.get("expected_result") or {}
    expected = expected_result.get("value")
    if not isinstance(expected, (int, float)):
        return False
    tolerance = case.get("tolerance", {})
    normalized_answer = (answer or "").translate(_SUPERSCRIPT_TRANSLATION)
    candidates = []
    for coefficient, exponent in _SCIENTIFIC_PATTERN.findall(normalized_answer):
        candidates.append(float(coefficient) * (10 ** int(exponent)))
    for percentage in _PERCENT_PATTERN.findall(normalized_answer):
        candidates.append(float(percentage) / 100.0)
    for numerator, denominator in _FRACTION_PATTERN.findall(normalized_answer):
        if int(denominator) != 0:
            candidates.append(int(numerator) / int(denominator))
    for match in _NUMBER_PATTERN.findall(normalized_answer):
        try:
            candidates.append(float(match.replace(",", "")))
        except ValueError:
            continue
    for actual in candidates:
        if math.isclose(
            actual,
            expected,
            abs_tol=tolerance.get("abs", 0.0),
            rel_tol=tolerance.get("rel", 0.0),
        ):
            return True
    return False


def _final_answer_correct(case: dict, experiment: dict, behavior_correct: bool):
    if experiment.get("status", "completed") != "completed":
        return False
    requirements = case.get("answer_requirements") or {"type": "manual"}
    requirement_type = requirements.get("type")
    answer = (experiment.get("final_answer") or "").strip()
    if requirement_type == "numeric":
        return _numeric_answer_correct(answer, case)
    if requirement_type == "concept_terms":
        normalized = answer.casefold()
        groups = requirements.get("required_term_groups") or []
        return bool(groups) and all(
            any(str(term).casefold() in normalized for term in group)
            for group in groups
        )
    if requirement_type == "behavior":
        return behavior_correct
    if requirement_type == "presence":
        return bool(answer)
    if requirement_type == "manual":
        return None
    raise ValueError(f"unsupported answer requirement type: {requirement_type}")


def _arguments_follow_reference(case: dict, chain: List[dict]) -> bool:
    expected_sequence = case.get("expected_call_sequence", [])
    if not expected_sequence:
        return not chain
    if [item.get("model_code") for item in chain] != expected_sequence:
        return False
    step_arguments = case.get("step_arguments") or {}
    if step_arguments:
        return all(
            item.get("generated_arguments", {}) == step_arguments.get(model_code, {})
            for item, model_code in zip(chain, expected_sequence)
        )
    return bool(chain) and chain[0].get("generated_arguments", {}) == case.get(
        "standard_arguments", {}
    )


class ToolCallingDataset:
    REQUIRED_FIELDS = {
        "case_id", "question", "category", "should_call_tool",
        "expected_models", "candidate_models", "standard_arguments",
        "argument_units", "expected_result", "tolerance",
        "expected_call_sequence", "step_arguments", "step_argument_units",
        "standard_answer", "applicability", "difficulty",
        "interference", "reference", "expected_outcome", "forced_model_code",
        "expected_final_behavior", "acceptable_actions", "answer_requirements",
    }

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "benchmarks", "tool_calling_cases.json"
        ))
        with open(self.path, encoding="utf-8") as handle:
            self.document = json.load(handle)
        self._validate()
        self._by_id = {case["case_id"]: case for case in self.document["cases"]}

    def _validate(self) -> None:
        cases = self.document.get("cases", [])
        if self.document.get("case_count") != len(cases):
            raise ValueError("tool-calling dataset case_count does not match cases")
        ids = [case.get("case_id") for case in cases]
        if len(ids) != len(set(ids)):
            raise ValueError("tool-calling dataset contains duplicate case IDs")
        categories = {case.get("category") for case in cases}
        if categories != REQUIRED_CATEGORIES:
            raise ValueError(f"tool-calling categories must be {sorted(REQUIRED_CATEGORIES)}")
        actual_coverage = dict(sorted(Counter(case["category"] for case in cases).items()))
        if self.document.get("category_coverage") != actual_coverage:
            raise ValueError("tool-calling category_coverage does not match cases")
        for case in cases:
            missing = self.REQUIRED_FIELDS - case.keys()
            if missing:
                raise ValueError(f"{case.get('case_id', '<unknown>')} missing fields: {sorted(missing)}")
            if not case["acceptable_actions"]:
                raise ValueError(f"{case['case_id']} acceptable_actions must not be empty")
            if case["answer_requirements"].get("type") not in {
                "numeric", "concept_terms", "behavior", "presence", "manual",
            }:
                raise ValueError(f"{case['case_id']} has unsupported answer requirements")

    @property
    def version(self) -> str:
        return self.document["dataset_version"]

    def get(self, case_id: str) -> Optional[dict]:
        case = self._by_id.get(case_id)
        return deepcopy(case) if case else None

    def list_cases(
        self,
        *,
        categories: Optional[Iterable[str]] = None,
        difficulties: Optional[Iterable[str]] = None,
        case_ids: Optional[Iterable[str]] = None,
        limit: Optional[int] = None,
    ) -> List[dict]:
        category_set = set(categories or [])
        difficulty_set = set(difficulties or [])
        id_set = set(case_ids or [])
        cases = []
        for case in self.document["cases"]:
            if category_set and case["category"] not in category_set:
                continue
            if difficulty_set and case["difficulty"] not in difficulty_set:
                continue
            if id_set and case["case_id"] not in id_set:
                continue
            cases.append(deepcopy(case))
        return cases[:limit] if limit else cases

    def summary(self) -> dict:
        return {
            "dataset_name": self.document["dataset_name"],
            "dataset_version": self.version,
            "case_count": self.document["case_count"],
            "category_coverage": deepcopy(self.document["category_coverage"]),
            "schema_version": self.document["schema_version"],
            "evaluator_version": EVALUATOR_VERSION,
        }


class BenchmarkService:
    METRIC_FIELDS = (
        "final_behavior_correct",
        "final_answer_correct",
        "semantic_case_passed",
        "path_compliance_correct",
        "strict_case_passed",
        "tool_decision_correct",
        "model_selection_correct",
        "arguments_exact_match",
        "unit_handling_correct",
        "argument_validation_correct",
        "outcome_correct",
        "numeric_result_correct",
        "case_passed",
    )

    def __init__(
        self,
        dataset: ToolCallingDataset,
        experiments: ExperimentService,
        store: TraceStore,
        experiment_engines: Optional[Dict[str, object]] = None,
    ):
        self.dataset = dataset
        self.experiments = experiments
        self.store = store
        self.experiment_engines = {"deterministic": experiments}
        self.experiment_engines.update(experiment_engines or {})

    @staticmethod
    def evaluate(case: dict, experiment: dict) -> dict:
        experiment_completed = experiment.get("status", "completed") == "completed"
        selected = experiment.get("selected_model")
        called = selected is not None
        expected_models = case.get("expected_models", [])
        expected_sequence = case.get("expected_call_sequence", [])
        chain = experiment.get("tool_call_chain") or []
        actual_sequence = [
            item.get("model_code") for item in chain if item.get("model_code")
        ]
        if not actual_sequence and selected:
            actual_sequence = [selected]
        actual_behavior = _final_behavior(experiment)
        final_behavior_correct = actual_behavior in case.get("acceptable_actions", [])
        final_answer_correct = _final_answer_correct(
            case, experiment, final_behavior_correct
        )
        requirement_type = (case.get("answer_requirements") or {}).get("type")
        if (
            not chain
            and requirement_type in {"numeric", "concept_terms"}
            and final_answer_correct
        ):
            # A correct substantive answer remains a direct answer even when
            # it contains caveats or an invitation to provide more context.
            actual_behavior = "direct_answer"
            final_behavior_correct = actual_behavior in case.get("acceptable_actions", [])

        tool_decision_correct = called == case["should_call_tool"]
        if case["should_call_tool"]:
            model_selection_correct = selected in expected_models
        else:
            model_selection_correct = not called

        if expected_sequence:
            matched = len(set(actual_sequence) & set(expected_sequence))
            call_sequence_recall = matched / len(set(expected_sequence))
        else:
            call_sequence_recall = 1.0 if not actual_sequence else 0.0

        generated_arguments = experiment.get("generated_arguments", {})
        arguments_exact_match = (
            generated_arguments == case.get("standard_arguments", {})
            if called else not case["should_call_tool"]
        )
        units = case.get("argument_units", {})
        unit_handling_correct = arguments_exact_match if units else None
        call_sequence_exact_match = actual_sequence == expected_sequence
        reference_arguments_match = _arguments_follow_reference(case, chain)

        validation = experiment.get("validation_result")
        execution = experiment.get("execution_result")
        expected_outcome = case["expected_outcome"]
        rejected = bool(
            (validation and not validation.get("valid", False))
            or (execution and execution.get("status") in {"rejected", "error"})
        )
        succeeded = bool(execution and execution.get("status") == "success")

        if expected_outcome in {"no_tool", "clarify"}:
            outcome_correct = not called
            argument_validation_correct = not called
        elif expected_outcome == "reject":
            outcome_correct = called and rejected
            argument_validation_correct = rejected
        elif expected_outcome == "multi_tool":
            outcome_correct = math.isclose(call_sequence_recall, 1.0)
            argument_validation_correct = bool(validation and validation.get("valid"))
        else:
            outcome_correct = succeeded
            argument_validation_correct = bool(validation and validation.get("valid"))

        numeric_result_correct = None
        expected_result = case.get("expected_result")
        if expected_result:
            if succeeded:
                try:
                    actual = _value_at_path(execution["output"], expected_result["path"])
                    expected = expected_result["value"]
                    tolerance = case.get("tolerance", {})
                    numeric_result_correct = math.isclose(
                        actual,
                        expected,
                        abs_tol=tolerance.get("abs", 0.0),
                        rel_tol=tolerance.get("rel", 0.0),
                    )
                except (KeyError, TypeError, ValueError):
                    numeric_result_correct = False
            else:
                numeric_result_correct = False

        # Transport/provider failures are operational failures, not valid
        # no-tool decisions.  Without this guard a failed request on a
        # no-tool case would be scored as a semantic success.
        if not experiment_completed:
            tool_decision_correct = False
            model_selection_correct = False
            arguments_exact_match = False
            unit_handling_correct = False if units else None
            argument_validation_correct = False
            outcome_correct = False
            call_sequence_recall = 0.0
            if expected_result:
                numeric_result_correct = False

        if not case["should_call_tool"]:
            path_compliance_correct = not called
        else:
            path_compliance_correct = call_sequence_exact_match and reference_arguments_match
            if expected_outcome == "reject":
                path_compliance_correct = path_compliance_correct and rejected
            elif expected_outcome == "multi_tool":
                path_compliance_correct = path_compliance_correct and all(
                    (item.get("execution_result") or {}).get("status") == "success"
                    for item in chain
                )
            else:
                path_compliance_correct = path_compliance_correct and succeeded
        path_compliance_correct = experiment_completed and path_compliance_correct
        semantic_case_passed = (
            experiment_completed and final_behavior_correct and final_answer_correct
            if final_answer_correct is not None else None
        )
        strict_case_passed = (
            experiment_completed
            and path_compliance_correct
            and final_behavior_correct
            and final_answer_correct
            if final_answer_correct is not None else None
        )
        call_records = chain or ([{
            "validation_result": validation,
            "execution_result": execution,
        }] if called else [])
        unsuccessful_call_count = sum(
            (item.get("execution_result") or {}).get("status") != "success"
            for item in call_records
        )
        unnecessary_call_count = len(call_records) if not case["should_call_tool"] else 0
        if not case["should_call_tool"]:
            ineffective_call_count = len(call_records)
        elif expected_outcome == "reject":
            ineffective_call_count = sum(
                not (
                    not (item.get("validation_result") or {}).get("valid", False)
                    or (item.get("execution_result") or {}).get("status")
                    in {"rejected", "error"}
                )
                for item in call_records
            )
        else:
            ineffective_call_count = unsuccessful_call_count

        return {
            "experiment_completed": experiment_completed,
            "evaluator_version": EVALUATOR_VERSION,
            "expected_final_behavior": case.get("expected_final_behavior"),
            "actual_final_behavior": actual_behavior,
            "final_behavior_correct": final_behavior_correct,
            "final_answer_correct": final_answer_correct,
            "semantic_case_passed": semantic_case_passed,
            "path_compliance_correct": path_compliance_correct,
            "strict_case_passed": strict_case_passed,
            "tool_decision_correct": tool_decision_correct,
            "model_selection_correct": model_selection_correct,
            "arguments_exact_match": arguments_exact_match,
            "unit_handling_correct": unit_handling_correct,
            "argument_validation_correct": argument_validation_correct,
            "outcome_correct": outcome_correct,
            "numeric_result_correct": numeric_result_correct,
            "call_sequence_recall": round(call_sequence_recall, 4),
            "call_sequence_exact_match": call_sequence_exact_match,
            "case_passed": semantic_case_passed,
            "case_passed_basis": (
                "semantic" if semantic_case_passed is not None else "manual_required"
            ),
            "actual_called": called,
            "actual_call_count": len(actual_sequence),
            "unsuccessful_call_count": unsuccessful_call_count,
            "unnecessary_call_count": unnecessary_call_count,
            "ineffective_call_count": ineffective_call_count,
            "duplicate_call_count": len(actual_sequence) - len(set(actual_sequence)),
            "actual_model": selected,
            "execution_status": execution.get("status") if execution else None,
            "error_code": execution.get("error_code") if execution else None,
        }

    @classmethod
    def _aggregate(cls, rows: List[dict]) -> dict:
        aggregate = {"experiment_count": len(rows)}
        completed_count = sum(
            bool(row["metrics"].get("experiment_completed")) for row in rows
        )
        aggregate["completed_experiment_count"] = completed_count
        aggregate["failed_experiment_count"] = len(rows) - completed_count
        aggregate["completion_rate"] = round(
            completed_count / len(rows), 4
        ) if rows else None
        automatically_scored_count = sum(
            row["metrics"].get("semantic_case_passed") is not None for row in rows
        )
        aggregate["automatically_scored_experiment_count"] = automatically_scored_count
        aggregate["manual_review_experiment_count"] = len(rows) - automatically_scored_count
        for field in cls.METRIC_FIELDS:
            values = [row["metrics"][field] for row in rows if row["metrics"][field] is not None]
            aggregate[f"{field}_rate"] = round(sum(bool(v) for v in values) / len(values), 4) if values else None
        aggregate["average_call_sequence_recall"] = round(
            sum(row["metrics"]["call_sequence_recall"] for row in rows) / len(rows), 4
        ) if rows else None
        total_calls = sum(row["metrics"]["actual_call_count"] for row in rows)
        aggregate["average_call_count"] = round(
            total_calls / len(rows), 4
        ) if rows else None
        aggregate["ineffective_call_rate"] = round(
            sum(row["metrics"]["ineffective_call_count"] for row in rows) / total_calls, 4
        ) if total_calls else 0.0 if rows else None
        aggregate["unsuccessful_call_rate"] = round(
            sum(row["metrics"]["unsuccessful_call_count"] for row in rows) / total_calls, 4
        ) if total_calls else 0.0 if rows else None
        aggregate["unnecessary_call_rate"] = round(
            sum(row["metrics"]["unnecessary_call_count"] for row in rows) / total_calls, 4
        ) if total_calls else 0.0 if rows else None
        aggregate["duplicate_call_rate"] = round(
            sum(row["metrics"]["duplicate_call_count"] for row in rows) / total_calls, 4
        ) if total_calls else 0.0 if rows else None
        aggregate["total_tokens"] = sum(
            (row.get("token_usage") or {}).get("total_tokens", 0) for row in rows
        )
        aggregate["average_latency_ms"] = round(
            sum(row["latency_ms"] for row in rows) / len(rows), 3
        ) if rows else None
        return aggregate

    def run(
        self,
        *,
        modes: Optional[List[str]] = None,
        case_ids: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        difficulties: Optional[List[str]] = None,
        max_cases: int = 120,
        engine: str = "deterministic",
        llm_name: Optional[str] = None,
        prompt_version: Optional[str] = None,
        result_validation_enabled: bool = True,
    ) -> dict:
        modes = modes or list(ExperimentService.MODES)
        invalid_modes = set(modes) - set(ExperimentService.MODES)
        if invalid_modes:
            raise ValueError(f"unsupported benchmark modes: {sorted(invalid_modes)}")
        if engine not in self.experiment_engines:
            raise ValueError(f"unsupported experiment engine: {engine}")
        if not 1 <= max_cases <= self.dataset.document["case_count"]:
            raise ValueError(f"max_cases must be between 1 and {self.dataset.document['case_count']}")

        cases = self.dataset.list_cases(
            categories=categories,
            difficulties=difficulties,
            case_ids=case_ids,
            limit=max_cases,
        )
        if not cases:
            raise ValueError("no benchmark cases matched the supplied filters")

        experiment_runner = self.experiment_engines[engine]
        if hasattr(experiment_runner, "ensure_ready"):
            experiment_runner.ensure_ready()
        effective_llm_name = llm_name or getattr(
            experiment_runner, "default_llm_name", "deterministic-orchestrator"
        )
        effective_prompt_version = prompt_version or (
            "m4.5-v1" if engine == "deepseek" else "benchmark-v1"
        )

        run_id = _identifier("BENCH")
        started = time.perf_counter()
        rows = []
        for case in cases:
            for mode in modes:
                forced_model = case["forced_model_code"] if mode == ExperimentService.MODE_FORCED else None
                reference_arguments = case.get("standard_arguments", {})
                experiment_arguments = (
                    reference_arguments
                    if getattr(experiment_runner, "uses_reference_arguments", True)
                    else {}
                )
                experiment = experiment_runner.run(
                    user_query=case["question"],
                    mode=mode,
                    model_code=forced_model,
                    arguments=experiment_arguments,
                    baseline_answer=(
                        "直接回答基线未接入外部大模型评分。"
                        if engine == "deterministic" and mode == ExperimentService.MODE_DIRECT
                        else ""
                    ),
                    llm_name=effective_llm_name,
                    prompt_version=effective_prompt_version,
                    result_validation_enabled=result_validation_enabled,
                    benchmark_case_id=case["case_id"],
                )
                metrics = self.evaluate(case, experiment)
                metrics["benchmark_run_id"] = run_id
                metrics["dataset_version"] = self.dataset.version
                experiment["metrics"] = metrics
                experiment["benchmark_run_id"] = run_id
                self.store.save_experiment(experiment)
                rows.append({
                    "run_id": run_id,
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "difficulty": case["difficulty"],
                    "mode": mode,
                    "engine": engine,
                    "experiment_id": experiment["experiment_id"],
                    "selected_model": experiment.get("selected_model"),
                    "latency_ms": experiment["latency_ms"],
                    "token_usage": experiment.get("token_usage"),
                    "metrics": metrics,
                })

        by_mode: Dict[str, list] = {}
        for mode in modes:
            by_mode[mode] = [row for row in rows if row["mode"] == mode]
        by_category: Dict[str, list] = {}
        for category in sorted({case["category"] for case in cases}):
            by_category[category] = [row for row in rows if row["category"] == category]

        return {
            "run_id": run_id,
            "dataset_version": self.dataset.version,
            "case_count": len(cases),
            "modes": modes,
            "configuration": {
                "engine": engine,
                "llm_name": effective_llm_name,
                "prompt_version": effective_prompt_version,
                "evaluator_version": EVALUATOR_VERSION,
                "result_validation_enabled": result_validation_enabled,
            },
            "total_experiments": len(rows),
            "summary": self._aggregate(rows),
            "summary_by_mode": {key: self._aggregate(value) for key, value in by_mode.items()},
            "summary_by_category": {key: self._aggregate(value) for key, value in by_category.items()},
            "runtime_ms": round((time.perf_counter() - started) * 1000, 2),
            "results": rows,
        }
