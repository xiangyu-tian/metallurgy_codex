"""Tool-calling benchmark dataset access and deterministic batch evaluation."""

from __future__ import annotations

import json
import math
import os
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


def _identifier(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def _value_at_path(payload, path: str):
    value = payload
    for part in path.split("."):
        value = value[part]
    return value


class ToolCallingDataset:
    REQUIRED_FIELDS = {
        "case_id", "question", "category", "should_call_tool",
        "expected_models", "candidate_models", "standard_arguments",
        "argument_units", "expected_result", "tolerance",
        "expected_call_sequence", "step_arguments", "step_argument_units",
        "standard_answer", "applicability", "difficulty",
        "interference", "reference", "expected_outcome", "forced_model_code",
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
        }


class BenchmarkService:
    METRIC_FIELDS = (
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
    ):
        self.dataset = dataset
        self.experiments = experiments
        self.store = store

    @staticmethod
    def evaluate(case: dict, experiment: dict) -> dict:
        selected = experiment.get("selected_model")
        called = selected is not None
        expected_models = case.get("expected_models", [])
        expected_sequence = case.get("expected_call_sequence", [])
        actual_sequence = [selected] if selected else []

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

        required = [
            tool_decision_correct,
            model_selection_correct,
            arguments_exact_match,
            argument_validation_correct,
            outcome_correct,
        ]
        if numeric_result_correct is not None:
            required.append(numeric_result_correct)
        if expected_outcome == "multi_tool":
            required.append(math.isclose(call_sequence_recall, 1.0))

        return {
            "tool_decision_correct": tool_decision_correct,
            "model_selection_correct": model_selection_correct,
            "arguments_exact_match": arguments_exact_match,
            "unit_handling_correct": unit_handling_correct,
            "argument_validation_correct": argument_validation_correct,
            "outcome_correct": outcome_correct,
            "numeric_result_correct": numeric_result_correct,
            "call_sequence_recall": round(call_sequence_recall, 4),
            "case_passed": all(required),
            "actual_called": called,
            "actual_model": selected,
            "execution_status": execution.get("status") if execution else None,
            "error_code": execution.get("error_code") if execution else None,
        }

    @classmethod
    def _aggregate(cls, rows: List[dict]) -> dict:
        aggregate = {"experiment_count": len(rows)}
        for field in cls.METRIC_FIELDS:
            values = [row["metrics"][field] for row in rows if row["metrics"][field] is not None]
            aggregate[f"{field}_rate"] = round(sum(bool(v) for v in values) / len(values), 4) if values else None
        aggregate["average_call_sequence_recall"] = round(
            sum(row["metrics"]["call_sequence_recall"] for row in rows) / len(rows), 4
        ) if rows else None
        aggregate["average_call_count"] = round(
            sum(1 if row["metrics"]["actual_called"] else 0 for row in rows) / len(rows), 4
        ) if rows else None
        aggregate["ineffective_call_rate"] = round(
            sum(
                1 for row in rows
                if row["metrics"]["actual_called"]
                and row["metrics"]["execution_status"] != "success"
            ) / len(rows), 4
        ) if rows else None
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
        llm_name: str = "deterministic-orchestrator",
        prompt_version: str = "benchmark-v1",
        result_validation_enabled: bool = True,
    ) -> dict:
        modes = modes or list(ExperimentService.MODES)
        invalid_modes = set(modes) - set(ExperimentService.MODES)
        if invalid_modes:
            raise ValueError(f"unsupported benchmark modes: {sorted(invalid_modes)}")
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

        run_id = _identifier("BENCH")
        started = time.perf_counter()
        rows = []
        for case in cases:
            for mode in modes:
                forced_model = case["forced_model_code"] if mode == ExperimentService.MODE_FORCED else None
                experiment = self.experiments.run(
                    user_query=case["question"],
                    mode=mode,
                    model_code=forced_model,
                    arguments=case.get("standard_arguments", {}),
                    baseline_answer="直接回答基线未接入外部大模型评分。" if mode == ExperimentService.MODE_DIRECT else "",
                    llm_name=llm_name,
                    prompt_version=prompt_version,
                    result_validation_enabled=result_validation_enabled,
                    benchmark_case_id=case["case_id"],
                )
                metrics = self.evaluate(case, experiment)
                metrics["benchmark_run_id"] = run_id
                metrics["dataset_version"] = self.dataset.version
                experiment["metrics"] = metrics
                self.store.save_experiment(experiment)
                rows.append({
                    "run_id": run_id,
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "difficulty": case["difficulty"],
                    "mode": mode,
                    "experiment_id": experiment["experiment_id"],
                    "selected_model": experiment.get("selected_model"),
                    "latency_ms": experiment["latency_ms"],
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
                "llm_name": llm_name,
                "prompt_version": prompt_version,
                "result_validation_enabled": result_validation_enabled,
            },
            "total_experiments": len(rows),
            "summary": self._aggregate(rows),
            "summary_by_mode": {key: self._aggregate(value) for key, value in by_mode.items()},
            "summary_by_category": {key: self._aggregate(value) for key, value in by_category.items()},
            "runtime_ms": round((time.perf_counter() - started) * 1000, 2),
            "results": rows,
        }
