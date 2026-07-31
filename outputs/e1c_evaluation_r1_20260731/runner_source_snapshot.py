"""Run the E1c six-condition end-to-end loss decomposition experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parents[1]
PROJECT_ROOT = HERE.parents[2]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from core_freeze.e1b_pilot.e1b_scoring import (  # noqa: E402
    extract_json_answer,
    parse_and_score,
)
from models_core import ModelRegistry  # noqa: E402
from models_core.llm_adapters import (  # noqa: E402
    DeepSeekOpenAIAdapter,
    LLMAdapterError,
    model_tools,
)


CONDITIONS = [
    "no_tool",
    "forced_verified_oracle_parameters",
    "model_gate_oracle_parameters",
    "oracle_gate_model_parameters",
    "direct_fc",
    "boundary_guided_fc",
]
TOOL_IDS = ["A001", "A002", "A003", "A004", "B019"]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_id() -> str:
    return f"E1C-RUN-{uuid.uuid4().hex[:16].upper()}"


def _tool_payload(result) -> dict[str, Any]:
    return {
        "success": result.success,
        "result": result.result,
        "error": result.error,
        "error_code": result.error_code,
        "boundary_check": {
            "passed": result.boundary_check.passed,
            "warnings": [
                {
                    "field": warning.field,
                    "message": warning.message,
                    "level": warning.level,
                }
                for warning in result.boundary_check.warnings
            ],
        },
        "runtime_ms": result.runtime_ms,
    }


def _schema_text(task: dict[str, Any]) -> str:
    return json.dumps(
        task["answer_schema"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _answer_messages(
    task: dict[str, Any],
    prompts: dict[str, Any],
    instruction: str,
) -> list[dict[str, str]]:
    system = (
        f"{prompts['answer_system']}\n答案Schema：{_schema_text(task)}\n"
        f"{instruction}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": task["problem_text"]},
    ]


def _final_messages(
    task: dict[str, Any],
    prompts: dict[str, Any],
    tool_id: str,
    tool_execution: dict[str, Any],
) -> list[dict[str, str]]:
    return _answer_messages(
        task,
        prompts,
        (
            f"{prompts['tool_result_instruction']}\n"
            f"工具ID：{tool_id}\n工具执行结果："
            f"{json.dumps(tool_execution, ensure_ascii=False, sort_keys=True)}"
        ),
    )


def _provider_call(
    *,
    adapter,
    messages: list[dict[str, Any]],
    run_config: dict[str, Any],
    purpose: str,
    tools: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    attempts = []
    max_attempts = int(run_config.get("provider_max_attempts", 1))
    backoff = float(run_config.get("retry_backoff_seconds", 0.0))
    for attempt in range(1, max_attempts + 1):
        try:
            response = adapter.complete(
                messages,
                tools=tools,
                tool_choice="auto" if tools else None,
                temperature=float(run_config["temperature"]),
                max_tokens=int(run_config["max_tokens"]),
            )
            attempts.append(
                {
                    "purpose": purpose,
                    "attempt": attempt,
                    "status": "completed",
                    "error": None,
                }
            )
            return response, attempts, None
        except LLMAdapterError as exc:
            attempts.append(
                {
                    "purpose": purpose,
                    "attempt": attempt,
                    "status": "provider_error",
                    "error": str(exc),
                }
            )
            if attempt == max_attempts:
                return None, attempts, str(exc)
            time.sleep(backoff * (2 ** (attempt - 1)))
    raise AssertionError("unreachable provider retry state")


def _tool_call_from_message(
    message: dict[str, Any],
) -> dict[str, Any] | None:
    calls = message.get("tool_calls")
    if not calls:
        return None
    if not isinstance(calls, list) or len(calls) != 1:
        return {
            "parse_status": "ambiguous",
            "tool_id": None,
            "parameters": None,
            "error": "expected exactly one tool call",
        }
    function = calls[0].get("function")
    if not isinstance(function, dict):
        return {
            "parse_status": "invalid",
            "tool_id": None,
            "parameters": None,
            "error": "tool call has no function object",
        }
    tool_id = function.get("name")
    raw_arguments = function.get("arguments")
    try:
        parameters = json.loads(raw_arguments)
    except (TypeError, json.JSONDecodeError):
        return {
            "parse_status": "invalid",
            "tool_id": tool_id,
            "parameters": None,
            "error": "tool arguments are not valid JSON",
        }
    if not isinstance(parameters, dict):
        return {
            "parse_status": "invalid",
            "tool_id": tool_id,
            "parameters": None,
            "error": "tool arguments must be an object",
        }
    return {
        "parse_status": "parsed",
        "tool_id": tool_id,
        "parameters": parameters,
        "error": None,
    }


def _parameters_equal(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and set(actual) == set(expected)
            and all(
                _parameters_equal(actual[key], expected[key])
                for key in expected
            )
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                _parameters_equal(a, b)
                for a, b in zip(actual, expected)
            )
        )
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and float(actual) == float(expected)
        )
    return type(actual) is type(expected) and actual == expected


def _score_payload(payload: dict[str, Any] | None, task: dict[str, Any]) -> dict[str, Any]:
    raw = (
        json.dumps(payload, ensure_ascii=False)
        if isinstance(payload, dict)
        else ""
    )
    return parse_and_score(raw, task["scoring_rule"])


def _failure_stage(record: dict[str, Any]) -> str:
    if record["status"] == "provider_error":
        return "provider_failure"
    if record.get("decision_parse_status") not in (None, "parsed", "oracle"):
        return "decision_parse_failure"
    if record.get("boundary_correct") is False:
        return "boundary_decision_error"
    if record.get("tool_selection_correct") is False:
        return "tool_selection_error"
    if record.get("parameter_parse_status") not in (None, "parsed", "oracle"):
        return "parameter_parse_failure"
    if record.get("parameter_exact_match") is False:
        return "parameter_value_error"
    execution = record.get("tool_execution")
    if execution is not None and execution.get("success") is not True:
        return "tool_execution_error"
    if record.get("parse_status") != "parsed":
        return "answer_parse_failure"
    if record.get("correct") is not True:
        return "final_answer_error"
    return "success"


def run_cell(
    *,
    task: dict[str, Any],
    condition: str,
    repeat: int,
    registry: ModelRegistry,
    adapter,
    prompts: dict[str, Any],
    run_config: dict[str, Any],
    tool_schemas: list[dict[str, Any]],
) -> dict[str, Any]:
    started = time.perf_counter()
    expected_action = task["frozen_policy_decision"]["action"]
    predicted_action = None
    decision_parse_status = None
    selected_tool_id = None
    tool_selection_correct = None
    generated_parameters = None
    parameter_parse_status = None
    parameter_exact_match = None
    tool_execution = None
    raw_answer = ""
    provider_calls: list[dict[str, Any]] = []
    response_metadata: list[dict[str, Any]] = []
    status = "completed"
    error_type = None
    error_message = None

    def call_provider(
        messages: list[dict[str, Any]],
        purpose: str,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        nonlocal status, error_type, error_message
        response, attempts, error = _provider_call(
            adapter=adapter,
            messages=messages,
            run_config=run_config,
            purpose=purpose,
            tools=tools,
        )
        provider_calls.extend(attempts)
        if response is None:
            status = "provider_error"
            error_type = "LLMAdapterError"
            error_message = error
            return None
        response_metadata.append(
            {
                "purpose": purpose,
                "id": response.get("id"),
                "model": response.get("model"),
                "finish_reason": response.get("finish_reason"),
                "usage": response.get("usage"),
            }
        )
        return response

    def invoke(tool_id: str, parameters: dict[str, Any]) -> dict[str, Any]:
        result = registry.invoke(tool_id, parameters)
        return _tool_payload(result)

    def final_from_tool(tool_id: str) -> None:
        nonlocal raw_answer
        response = call_provider(
            _final_messages(
                task,
                prompts,
                tool_id,
                tool_execution,
            ),
            "final_answer_from_tool",
        )
        if response:
            raw_answer = response["message"].get("content") or ""

    try:
        if condition == "no_tool":
            response = call_provider(
                _answer_messages(
                    task,
                    prompts,
                    prompts["no_tool_instruction"],
                ),
                "direct_answer",
            )
            if response:
                raw_answer = response["message"].get("content") or ""

        elif condition == "forced_verified_oracle_parameters":
            selected_tool_id = task["source_tool_id"]
            generated_parameters = task["expected_parameters"]
            parameter_parse_status = "oracle"
            parameter_exact_match = True
            tool_execution = invoke(selected_tool_id, generated_parameters)
            final_from_tool(selected_tool_id)

        elif condition == "model_gate_oracle_parameters":
            gate_system = (
                f"{prompts['gate_system']}\n{prompts['boundary_policy']}\n"
                f"答案Schema：{_schema_text(task)}"
            )
            response = call_provider(
                [
                    {"role": "system", "content": gate_system},
                    {"role": "user", "content": task["problem_text"]},
                ],
                "boundary_decision",
            )
            if response:
                gate_raw = response["message"].get("content") or ""
                parsed = extract_json_answer(gate_raw)
                decision_parse_status = parsed["status"]
                decision = parsed["answer"]
                if isinstance(decision, dict):
                    predicted_action = decision.get("action")
                    if predicted_action not in {
                        "CALL_VERIFIED_TOOL",
                        "ANSWER_WITHOUT_TOOL",
                    }:
                        decision_parse_status = "invalid"
                    elif predicted_action == "CALL_VERIFIED_TOOL":
                        selected_tool_id = task["source_tool_id"]
                        generated_parameters = task["expected_parameters"]
                        parameter_parse_status = "oracle"
                        parameter_exact_match = True
                        tool_execution = invoke(
                            selected_tool_id,
                            generated_parameters,
                        )
                        final_from_tool(selected_tool_id)
                    else:
                        answer = decision.get("answer")
                        raw_answer = (
                            json.dumps(answer, ensure_ascii=False)
                            if isinstance(answer, dict)
                            else ""
                        )

        elif condition == "oracle_gate_model_parameters":
            predicted_action = expected_action
            decision_parse_status = "oracle"
            if expected_action == "ANSWER_WITHOUT_TOOL":
                response = call_provider(
                    _answer_messages(
                        task,
                        prompts,
                        prompts["no_tool_instruction"],
                    ),
                    "oracle_gate_direct_answer",
                )
                if response:
                    raw_answer = response["message"].get("content") or ""
            else:
                selected_tool_id = task["source_tool_id"]
                schema = next(
                    row["function"]["parameters"]
                    for row in tool_schemas
                    if row["function"]["name"] == selected_tool_id
                )
                response = call_provider(
                    [
                        {
                            "role": "system",
                            "content": (
                                f"{prompts['parameter_system']}\n"
                                f"目标工具：{selected_tool_id}\n"
                                "参数Schema："
                                f"{json.dumps(schema, ensure_ascii=False, sort_keys=True)}"
                            ),
                        },
                        {"role": "user", "content": task["problem_text"]},
                    ],
                    "parameter_generation",
                )
                if response:
                    parsed = extract_json_answer(
                        response["message"].get("content") or ""
                    )
                    parameter_parse_status = parsed["status"]
                    generated_parameters = parsed["answer"]
                    if isinstance(generated_parameters, dict):
                        parameter_exact_match = _parameters_equal(
                            generated_parameters,
                            task["expected_parameters"],
                        )
                        tool_execution = invoke(
                            selected_tool_id,
                            generated_parameters,
                        )
                        final_from_tool(selected_tool_id)

        elif condition in {"direct_fc", "boundary_guided_fc"}:
            instruction = prompts["direct_fc_system"]
            if condition == "boundary_guided_fc":
                instruction = (
                    f"{prompts['boundary_guided_fc_system']}\n"
                    f"{prompts['boundary_policy']}"
                )
            response = call_provider(
                _answer_messages(task, prompts, instruction),
                "autonomous_decision_and_parameters",
                tools=tool_schemas,
            )
            if response:
                message = response["message"]
                call = _tool_call_from_message(message)
                if call is None:
                    predicted_action = "ANSWER_WITHOUT_TOOL"
                    decision_parse_status = "parsed"
                    raw_answer = message.get("content") or ""
                else:
                    predicted_action = "CALL_VERIFIED_TOOL"
                    decision_parse_status = "parsed"
                    selected_tool_id = call["tool_id"]
                    generated_parameters = call["parameters"]
                    parameter_parse_status = call["parse_status"]
                    if selected_tool_id is not None:
                        tool_selection_correct = (
                            selected_tool_id == task["source_tool_id"]
                        )
                    if isinstance(generated_parameters, dict):
                        parameter_exact_match = _parameters_equal(
                            generated_parameters,
                            task["expected_parameters"],
                        )
                    if (
                        call["parse_status"] == "parsed"
                        and selected_tool_id in TOOL_IDS
                        and isinstance(generated_parameters, dict)
                    ):
                        tool_execution = invoke(
                            selected_tool_id,
                            generated_parameters,
                        )
                        final_from_tool(selected_tool_id)
        else:
            raise ValueError(f"unsupported E1c condition: {condition}")
    except Exception as exc:
        status = "internal_error"
        error_type = type(exc).__name__
        error_message = str(exc)

    boundary_correct = (
        predicted_action == expected_action
        if predicted_action is not None
        else None
    )
    scoring = parse_and_score(raw_answer, task["scoring_rule"])
    record = {
        "cell_id": f"{task['task_id']}::{condition}::R{repeat}",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "task_id": task["task_id"],
        "base_task_group_id": task["base_task_group_id"],
        "split": task["split"],
        "source_tool_id": task["source_tool_id"],
        "precision_policy": task["precision_policy"],
        "condition": condition,
        "model_run_repeat": repeat,
        "provider": run_config["provider"],
        "model": run_config["model"],
        "prompt_version": run_config["prompt_version"],
        "status": status,
        "error_type": error_type,
        "error_message": error_message,
        "expected_action": expected_action,
        "predicted_action": predicted_action,
        "decision_parse_status": decision_parse_status,
        "boundary_correct": boundary_correct,
        "selected_tool_id": selected_tool_id,
        "tool_selection_correct": tool_selection_correct,
        "generated_parameters": generated_parameters,
        "parameter_parse_status": parameter_parse_status,
        "parameter_exact_match": parameter_exact_match,
        "tool_execution": tool_execution,
        "raw_answer": raw_answer,
        "provider_call_count": len(
            {
                row["purpose"]
                for row in provider_calls
                if row["status"] == "completed"
            }
        ),
        "provider_attempt_count": len(provider_calls),
        "provider_attempts": provider_calls,
        "response_metadata": response_metadata,
        **scoring,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    record["primary_failure_stage"] = _failure_stage(record)
    return record


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_condition = {}
    for condition in CONDITIONS:
        rows = [row for row in records if row["condition"] == condition]
        decision_rows = [
            row for row in rows if row["boundary_correct"] is not None
        ]
        selection_rows = [
            row
            for row in rows
            if row["tool_selection_correct"] is not None
        ]
        parameter_rows = [
            row for row in rows if row["parameter_exact_match"] is not None
        ]
        by_condition[condition] = {
            "cell_count": len(rows),
            "completed_count": sum(
                row["status"] == "completed" for row in rows
            ),
            "correct_count": sum(row["correct"] is True for row in rows),
            "accuracy": (
                sum(row["correct"] is True for row in rows) / len(rows)
                if rows
                else None
            ),
            "call_count": sum(
                row["predicted_action"] == "CALL_VERIFIED_TOOL"
                for row in rows
            ),
            "boundary_evaluable_count": len(decision_rows),
            "boundary_correct_count": sum(
                row["boundary_correct"] is True for row in decision_rows
            ),
            "tool_selection_evaluable_count": len(selection_rows),
            "tool_selection_correct_count": sum(
                row["tool_selection_correct"] is True
                for row in selection_rows
            ),
            "parameter_evaluable_count": len(parameter_rows),
            "parameter_exact_count": sum(
                row["parameter_exact_match"] is True
                for row in parameter_rows
            ),
            "provider_call_count": sum(
                row["provider_call_count"] for row in rows
            ),
            "provider_attempt_count": sum(
                row["provider_attempt_count"] for row in rows
            ),
            "failure_stage_counts": dict(
                sorted(
                    Counter(
                        row["primary_failure_stage"] for row in rows
                    ).items()
                )
            ),
        }
    return {
        "cell_count": len(records),
        "condition_count": len(CONDITIONS),
        "by_condition": by_condition,
        "provider_call_count": sum(
            row["provider_call_count"] for row in records
        ),
        "provider_attempt_count": sum(
            row["provider_attempt_count"] for row in records
        ),
        "retried_cell_count": sum(
            row["provider_attempt_count"] > row["provider_call_count"]
            for row in records
        ),
        "status": (
            "completed"
            if records and all(row["status"] == "completed" for row in records)
            else "completed_with_failures"
        ),
        "confirmatory_inference_allowed": False,
    }


def validate_run_scope(
    tasks_doc: dict[str, Any],
    prompts: dict[str, Any],
    run_config: dict[str, Any],
    execution_authorization: dict[str, Any] | None = None,
) -> None:
    if tasks_doc.get("dataset_id") != run_config.get("dataset_id"):
        raise ValueError("task/config dataset id mismatch")
    if prompts.get("prompt_version") != run_config.get("prompt_version"):
        raise ValueError("prompt/config version mismatch")
    if tasks_doc.get("protocol_sha256") != run_config.get("protocol_sha256"):
        raise ValueError("task/config protocol hash mismatch")
    if tasks_doc.get("frozen_policy_sha256") != run_config.get(
        "frozen_policy_sha256"
    ):
        raise ValueError("task/config policy hash mismatch")
    if run_config.get("conditions") != CONDITIONS:
        raise ValueError("run conditions differ from frozen order")
    selected_split = run_config.get("selected_split")
    if any(task.get("split") != selected_split for task in tasks_doc["tasks"]):
        raise ValueError("task snapshot contains rows outside selected split")
    if (
        selected_split == "runner_development"
        and run_config.get("evaluation_split_opened") is not False
    ):
        raise ValueError("development run must keep evaluation sealed")
    if selected_split == "runner_development":
        if tasks_doc.get("evaluation_split_opened") is not False:
            raise ValueError("development task snapshot opens evaluation")
        if execution_authorization is not None:
            raise ValueError("development run must not use evaluation authorization")
    elif selected_split == "end_to_end_evaluation":
        if run_config.get("evaluation_split_opened") is not True:
            raise ValueError("evaluation config does not open evaluation")
        if tasks_doc.get("evaluation_split_opened") is not True:
            raise ValueError("evaluation task snapshot is not opened")
        if run_config.get("requires_external_api_authorization") is not True:
            raise ValueError("evaluation config must require external API authorization")
        if execution_authorization is None:
            raise ValueError("evaluation execution authorization is required")
        if execution_authorization.get("decision") != (
            "authorized_to_execute_evaluation"
        ):
            raise ValueError("evaluation execution is not authorized")
        if execution_authorization.get("dataset_id") != tasks_doc.get(
            "dataset_id"
        ):
            raise ValueError("authorization dataset id mismatch")
        if execution_authorization.get("run_config_id") != run_config.get(
            "run_config_id"
        ):
            raise ValueError("authorization run config id mismatch")
        if execution_authorization.get("authorized_task_count") != len(
            tasks_doc["tasks"]
        ):
            raise ValueError("authorization task count mismatch")
        if execution_authorization.get("endpoint") != run_config.get(
            "openai_base_url"
        ):
            raise ValueError("authorization endpoint mismatch")
        if execution_authorization.get("model") != run_config.get("model"):
            raise ValueError("authorization model mismatch")
    else:
        raise ValueError("unsupported E1c split")
    if run_config.get("policy_revision_allowed") is not False:
        raise ValueError("run config allows policy revision")


def validate_execution_authorization_hashes(
    *,
    execution_authorization: dict[str, Any],
    tasks_path: Path,
    prompts_path: Path,
    config_path: Path,
) -> None:
    expected_hashes = {
        "task_snapshot_sha256": file_hash(tasks_path),
        "prompt_sha256": file_hash(prompts_path),
        "run_config_sha256": file_hash(config_path),
        "runner_sha256": file_hash(Path(__file__)),
    }
    for field, actual in expected_hashes.items():
        if execution_authorization.get(field) != actual:
            raise ValueError(f"authorization {field} mismatch")


def run_experiment(
    *,
    tasks_doc: dict[str, Any],
    prompts: dict[str, Any],
    run_config: dict[str, Any],
    registry: ModelRegistry,
    adapter,
    repeats: int,
    max_tasks: int | None = None,
    conditions: list[str] | None = None,
    execution_authorization: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    validate_run_scope(
        tasks_doc,
        prompts,
        run_config,
        execution_authorization,
    )
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    selected_conditions = conditions or CONDITIONS
    if not selected_conditions or any(
        condition not in CONDITIONS for condition in selected_conditions
    ):
        raise ValueError("invalid selected conditions")
    tasks = tasks_doc["tasks"]
    if max_tasks is not None:
        if max_tasks < 1:
            raise ValueError("max_tasks must be at least 1")
        tasks = tasks[:max_tasks]
    tool_schemas = model_tools(registry, TOOL_IDS)
    if [row["function"]["name"] for row in tool_schemas] != TOOL_IDS:
        raise ValueError("five-tool schema set is not frozen")

    records = []
    for repeat in range(1, repeats + 1):
        for task in tasks:
            for condition in selected_conditions:
                records.append(
                    run_cell(
                        task=task,
                        condition=condition,
                        repeat=repeat,
                        registry=registry,
                        adapter=adapter,
                        prompts=prompts,
                        run_config=run_config,
                        tool_schemas=tool_schemas,
                    )
                )
    return records, summarize(records)


def write_outputs(
    *,
    output_dir: Path,
    tasks_path: Path,
    prompts_path: Path,
    config_path: Path,
    tasks_doc: dict[str, Any],
    run_config: dict[str, Any],
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    registry: ModelRegistry,
    adapter_configuration: dict[str, Any],
    execution_authorization_path: Path | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    run_id = _run_id()
    snapshots = {
        "tasks": (tasks_path, output_dir / "task_source_snapshot.json"),
        "prompts": (prompts_path, output_dir / "prompt_source_snapshot.json"),
        "run_config": (config_path, output_dir / "run_config_snapshot.json"),
        "runner": (Path(__file__), output_dir / "runner_source_snapshot.py"),
        "scoring": (
            HERE.parent / "e1b_pilot" / "e1b_scoring.py",
            output_dir / "scoring_source_snapshot.py",
        ),
    }
    if execution_authorization_path is not None:
        snapshots["execution_authorization"] = (
            execution_authorization_path,
            output_dir / "execution_authorization_snapshot.json",
        )
    for source, target in snapshots.values():
        shutil.copyfile(source, target)
    schema_path = output_dir / "five_tool_schema_snapshot.json"
    schema_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "tool_ids": TOOL_IDS,
                "tools": model_tools(registry, TOOL_IDS),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    records_path = output_dir / "run_records.jsonl"
    with records_path.open("x", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(
                json.dumps({"run_id": run_id, **record}, ensure_ascii=False)
                + "\n"
            )
    report_path = output_dir / "run_report.json"
    report = {
        "schema_version": "1.0",
        "run_id": run_id,
        "dataset_id": tasks_doc["dataset_id"],
        "run_config_id": run_config["run_config_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "task_source_sha256": file_hash(tasks_path),
        "protocol_sha256": run_config["protocol_sha256"],
        "prompt_source_sha256": file_hash(prompts_path),
        "run_config_sha256": file_hash(config_path),
        "selected_split": run_config["selected_split"],
        "execution_authorization_id": (
            load_json(execution_authorization_path).get("authorization_id")
            if execution_authorization_path is not None
            else None
        ),
        "adapter_configuration": adapter_configuration,
        "summary": summary,
        "evaluation_split_opened": (
            run_config["selected_split"] == "end_to_end_evaluation"
        ),
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest_path = output_dir / "artifact_manifest.json"
    artifacts = [
        target for _, target in snapshots.values()
    ] + [schema_path, records_path, report_path]
    manifest = {
        "schema_version": "1.0",
        "run_id": run_id,
        "artifacts": [
            {"filename": path.name, "sha256": file_hash(path)}
            for path in artifacts
        ],
        "evaluation_split_opened": (
            run_config["selected_split"] == "end_to_end_evaluation"
        ),
        "core_frozen": False,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tasks",
        type=Path,
        default=(
            PROJECT_ROOT
            / "outputs"
            / "e1c_development_v1_20260731"
            / "e1c_development_tasks_v1.json"
        ),
    )
    parser.add_argument(
        "--prompts",
        type=Path,
        default=HERE / "prompts_v1.json",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=HERE / "run_config_development_v1.json",
    )
    parser.add_argument("--execution-authorization", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repeats", type=int)
    parser.add_argument("--max-tasks", type=int)
    parser.add_argument(
        "--conditions",
        nargs="+",
        choices=CONDITIONS,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tasks_doc = load_json(args.tasks)
    prompts = load_json(args.prompts)
    run_config = load_json(args.config)
    execution_authorization = (
        load_json(args.execution_authorization)
        if args.execution_authorization is not None
        else None
    )
    if file_hash(args.prompts) != run_config.get("prompt_sha256"):
        raise RuntimeError("frozen prompt hash mismatch")
    validate_run_scope(
        tasks_doc,
        prompts,
        run_config,
        execution_authorization,
    )
    if run_config.get("selected_split") == "end_to_end_evaluation":
        if args.execution_authorization is None:
            raise RuntimeError("evaluation execution authorization is required")
        if args.max_tasks is not None or args.conditions is not None:
            raise RuntimeError(
                "formal evaluation forbids task or condition subsampling"
            )
        validate_execution_authorization_hashes(
            execution_authorization=execution_authorization,
            tasks_path=args.tasks,
            prompts_path=args.prompts,
            config_path=args.config,
        )
    adapter = DeepSeekOpenAIAdapter.from_environment()
    adapter.timeout = float(run_config["timeout_seconds"])
    if adapter.model != run_config["model"]:
        raise RuntimeError("configured model mismatch")
    if adapter.base_url != run_config["openai_base_url"]:
        raise RuntimeError("configured base URL mismatch")
    if adapter.thinking != run_config["thinking"]:
        raise RuntimeError("configured thinking mismatch")
    adapter.ensure_ready()
    registry = ModelRegistry()
    registry.discover()
    repeats_field = (
        "evaluation_repeats"
        if run_config.get("selected_split") == "end_to_end_evaluation"
        else "development_repeats"
    )
    frozen_repeats = int(run_config[repeats_field])
    if (
        run_config.get("selected_split") == "end_to_end_evaluation"
        and args.repeats is not None
        and args.repeats != frozen_repeats
    ):
        raise RuntimeError("formal evaluation repeat override is forbidden")
    repeats = args.repeats if args.repeats is not None else frozen_repeats
    records, summary = run_experiment(
        tasks_doc=tasks_doc,
        prompts=prompts,
        run_config=run_config,
        registry=registry,
        adapter=adapter,
        repeats=repeats,
        max_tasks=args.max_tasks,
        conditions=args.conditions,
        execution_authorization=execution_authorization,
    )
    report = write_outputs(
        output_dir=args.output_dir,
        tasks_path=args.tasks,
        prompts_path=args.prompts,
        config_path=args.config,
        tasks_doc=tasks_doc,
        run_config=run_config,
        records=records,
        summary=summary,
        registry=registry,
        adapter_configuration=adapter.configuration(),
        execution_authorization_path=args.execution_authorization,
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
