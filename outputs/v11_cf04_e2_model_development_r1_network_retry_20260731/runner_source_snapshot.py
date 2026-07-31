"""Run the E2 contract-readiness development pilot."""

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
)
from models_core.llm_adapters import (  # noqa: E402
    DeepSeekOpenAIAdapter,
    LLMAdapterError,
)


TASKS_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_pilot_20260731"
    / "e2_pilot_tasks.json"
)
CONTRACTS_PATH = (
    HERE.parent / "verified_core" / "contracts_v1.json"
)
POLICY_PATH = HERE / "policy_v1.json"
PROMPTS_PATH = HERE / "prompts_v1.json"
OUTPUT_SCHEMA_PATH = HERE / "output_schema_v1.json"
CONFIG_PATH = HERE / "run_config_development_v1.json"
AUTHORIZATION_PATH = HERE / "execution_authorization_development_v1.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_id() -> str:
    return f"E2-DEV-RUN-{uuid.uuid4().hex[:16].upper()}"


def contract_view(contract: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "contract_id",
        "tool_id",
        "tool_version",
        "tool_status",
        "scientific_function",
        "required_inputs",
        "optional_inputs",
        "input_units",
        "supported_systems",
        "composition_constraints",
        "model_assumptions",
        "data_or_model_version",
        "service_status",
        "validation_rules",
        "verification_scope",
        "known_limitations",
    )
    return {key: contract.get(key) for key in keys}


def build_messages(
    task: dict[str, Any],
    contract: dict[str, Any],
    prompts: dict[str, Any],
) -> list[dict[str, str]]:
    contract_json = json.dumps(
        contract_view(contract),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    request_json = json.dumps(
        task["structured_state"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    user = prompts["user_template"].format(
        contract_json=contract_json,
        request_json=request_json,
    )
    return [
        {"role": "system", "content": prompts["system"]},
        {"role": "user", "content": user},
    ]


def validate_output(
    value: Any,
    output_schema: dict[str, Any],
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return False, ["output is not an object"]
    required = set(output_schema["required"])
    allowed_properties = set(output_schema["properties"])
    if set(value) != required:
        errors.append(
            f"output keys must be exactly {sorted(required)}"
        )
    flags = value.get("flags")
    flag_enum = set(
        output_schema["properties"]["flags"]["items"]["enum"]
    )
    if not isinstance(flags, list):
        errors.append("flags is not an array")
    else:
        if len(flags) != len(set(flags)):
            errors.append("flags contains duplicates")
        if any(not isinstance(flag, str) for flag in flags):
            errors.append("flags contains non-string values")
        unknown = {
            flag for flag in flags if isinstance(flag, str)
        } - flag_enum
        if unknown:
            errors.append(f"unknown flags: {sorted(unknown)}")
    for field in ("primary_status", "action"):
        if value.get(field) not in set(
            output_schema["properties"][field]["enum"]
        ):
            errors.append(f"invalid {field}")
    if set(value) - allowed_properties:
        errors.append("output contains additional properties")
    return not errors, errors


def _jaccard(actual: list[str], expected: list[str]) -> float:
    actual_set = set(actual)
    expected_set = set(expected)
    union = actual_set | expected_set
    return len(actual_set & expected_set) / len(union) if union else 1.0


def score_prediction(
    parsed: Any,
    task: dict[str, Any],
    output_schema: dict[str, Any],
) -> dict[str, Any]:
    valid, validation_errors = validate_output(parsed, output_schema)
    if not valid:
        return {
            "schema_valid": False,
            "schema_errors": validation_errors,
            "predicted_flags": None,
            "predicted_primary_status": None,
            "predicted_action": None,
            "flags_exact": False,
            "flags_jaccard": 0.0,
            "primary_status_correct": False,
            "action_correct": False,
        }
    predicted_flags = parsed["flags"]
    return {
        "schema_valid": True,
        "schema_errors": [],
        "predicted_flags": predicted_flags,
        "predicted_primary_status": parsed["primary_status"],
        "predicted_action": parsed["action"],
        "flags_exact": set(predicted_flags) == set(task["expected_flags"]),
        "flags_jaccard": _jaccard(
            predicted_flags,
            task["expected_flags"],
        ),
        "primary_status_correct": (
            parsed["primary_status"] == task["primary_status"]
        ),
        "action_correct": (
            parsed["action"] == task["policy_expected_action"]
        ),
    }


def provider_call(
    adapter,
    messages: list[dict[str, str]],
    config: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    attempts = []
    max_attempts = int(config["provider_max_attempts"])
    backoff = float(config["retry_backoff_seconds"])
    for attempt in range(1, max_attempts + 1):
        try:
            response = adapter.complete(
                messages,
                temperature=float(config["temperature"]),
                max_tokens=int(config["max_tokens"]),
            )
            attempts.append(
                {
                    "attempt": attempt,
                    "status": "completed",
                    "error": None,
                }
            )
            return response, attempts, None
        except LLMAdapterError as exc:
            attempts.append(
                {
                    "attempt": attempt,
                    "status": "provider_error",
                    "error": str(exc),
                }
            )
            if attempt == max_attempts:
                return None, attempts, str(exc)
            time.sleep(backoff * (2 ** (attempt - 1)))
    raise AssertionError("unreachable provider retry state")


def run_cell(
    *,
    task: dict[str, Any],
    contract: dict[str, Any],
    prompts: dict[str, Any],
    output_schema: dict[str, Any],
    config: dict[str, Any],
    adapter,
) -> dict[str, Any]:
    started = time.perf_counter()
    messages = build_messages(task, contract, prompts)
    response, attempts, error = provider_call(adapter, messages, config)
    raw_output = ""
    parse_status = "provider_error"
    parsed_output = None
    status = "provider_error" if response is None else "completed"
    response_metadata = None
    if response is not None:
        raw_output = response["message"].get("content") or ""
        parsed = extract_json_answer(raw_output)
        parse_status = parsed["status"]
        parsed_output = parsed["answer"]
        response_metadata = {
            "id": response.get("id"),
            "model": response.get("model"),
            "finish_reason": response.get("finish_reason"),
            "usage": response.get("usage"),
        }
    scoring = score_prediction(parsed_output, task, output_schema)
    return {
        "cell_id": f"{task['task_id']}::model_policy::R1",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "task_id": task["task_id"],
        "base_task_id": task["base_task_id"],
        "base_task_group_id": task["base_task_group_id"],
        "source_tool_id": task["source_tool_id"],
        "contract_id": task["contract_id"],
        "contract_hash": task["contract_hash"],
        "mutation_types": task["mutation_types"],
        "expected_flags": task["expected_flags"],
        "expected_primary_status": task["primary_status"],
        "expected_action": task["policy_expected_action"],
        "condition": "model_policy",
        "model_run_repeat": 1,
        "provider": config["provider"],
        "model": config["model"],
        "prompt_version": config["prompt_version"],
        "status": status,
        "error_type": "LLMAdapterError" if error else None,
        "error_message": error,
        "provider_attempt_count": len(attempts),
        "provider_attempts": attempts,
        "raw_output": raw_output,
        "parse_status": parse_status,
        "parsed_output": parsed_output,
        "response_metadata": response_metadata,
        **scoring,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def flag_metrics(
    records: list[dict[str, Any]],
    supported_flags: list[str],
) -> dict[str, Any]:
    rows = []
    for flag in supported_flags:
        tp = sum(
            flag in (row["predicted_flags"] or [])
            and flag in row["expected_flags"]
            for row in records
        )
        fp = sum(
            flag in (row["predicted_flags"] or [])
            and flag not in row["expected_flags"]
            for row in records
        )
        fn = sum(
            flag not in (row["predicted_flags"] or [])
            and flag in row["expected_flags"]
            for row in records
        )
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        rows.append(
            {
                "flag": flag,
                "support": tp + fn,
                "true_positive": tp,
                "false_positive": fp,
                "false_negative": fn,
                "precision": precision,
                "recall": recall,
                "f1": f1,
            }
        )
    return {
        "by_flag": rows,
        "supported_flag_macro_f1": (
            sum(row["f1"] for row in rows) / len(rows)
            if rows
            else None
        ),
    }


def summarize(
    records: list[dict[str, Any]],
    supported_flags: list[str],
) -> dict[str, Any]:
    completed = [
        row for row in records if row["status"] == "completed"
    ]
    expected_clarify = [
        row for row in completed if row["expected_action"] == "clarify"
    ]
    ood_flags = {
        "contract_defined_out_of_domain",
        "contract_defined_unsupported_system",
        "model_card_defined_ood",
        "version_mismatch",
    }
    ood_rows = [
        row
        for row in completed
        if set(row["expected_flags"]) & ood_flags
    ]
    invalid_execution_rows = [
        row
        for row in completed
        if row["expected_action"] != "call"
    ]
    by_action = {}
    for action in ("call", "clarify", "refuse"):
        rows = [
            row for row in completed if row["expected_action"] == action
        ]
        by_action[action] = {
            "task_count": len(rows),
            "correct_count": sum(row["action_correct"] for row in rows),
            "accuracy": (
                sum(row["action_correct"] for row in rows) / len(rows)
                if rows
                else None
            ),
            "predicted_action_counts": dict(
                sorted(
                    Counter(
                        row["predicted_action"] or "__INVALID__"
                        for row in rows
                    ).items()
                )
            ),
        }
    flags = flag_metrics(completed, supported_flags)
    return {
        "cell_count": len(records),
        "completed_count": len(completed),
        "provider_failure_count": sum(
            row["status"] == "provider_error" for row in records
        ),
        "retried_cell_count": sum(
            row["provider_attempt_count"] > 1 for row in records
        ),
        "schema_valid_count": sum(row["schema_valid"] for row in completed),
        "schema_valid_rate": (
            sum(row["schema_valid"] for row in completed) / len(completed)
            if completed
            else None
        ),
        "flags_exact_count": sum(row["flags_exact"] for row in completed),
        "flags_exact_accuracy": (
            sum(row["flags_exact"] for row in completed) / len(completed)
            if completed
            else None
        ),
        "mean_flags_jaccard": (
            sum(row["flags_jaccard"] for row in completed) / len(completed)
            if completed
            else None
        ),
        "supported_flag_macro_f1": flags["supported_flag_macro_f1"],
        "flag_metrics": flags["by_flag"],
        "primary_status_accuracy": (
            sum(row["primary_status_correct"] for row in completed)
            / len(completed)
            if completed
            else None
        ),
        "action_accuracy": (
            sum(row["action_correct"] for row in completed) / len(completed)
            if completed
            else None
        ),
        "by_expected_action": by_action,
        "invalid_execution_rate": (
            sum(row["predicted_action"] == "call" for row in invalid_execution_rows)
            / len(invalid_execution_rows)
            if invalid_execution_rows
            else None
        ),
        "premature_call_rate": (
            sum(row["predicted_action"] == "call" for row in expected_clarify)
            / len(expected_clarify)
            if expected_clarify
            else None
        ),
        "out_of_domain_call_rate": (
            sum(row["predicted_action"] == "call" for row in ood_rows)
            / len(ood_rows)
            if ood_rows
            else None
        ),
        "provider_attempt_count": sum(
            row["provider_attempt_count"] for row in records
        ),
        "status": (
            "completed"
            if records and len(completed) == len(records)
            else "completed_with_failures"
        ),
        "confirmatory_inference_allowed": False,
    }


def validate_inputs(
    tasks_doc: dict[str, Any],
    contracts_doc: dict[str, Any],
    prompts: dict[str, Any],
    output_schema: dict[str, Any],
    policy: dict[str, Any],
    config: dict[str, Any],
) -> None:
    bindings = {
        "dataset_id": tasks_doc["dataset_id"],
        "task_source_sha256": file_hash(TASKS_PATH),
        "contracts_sha256": file_hash(CONTRACTS_PATH),
        "policy_sha256": file_hash(POLICY_PATH),
        "prompt_sha256": file_hash(PROMPTS_PATH),
        "output_schema_sha256": file_hash(OUTPUT_SCHEMA_PATH),
    }
    for field, actual in bindings.items():
        if config.get(field) != actual:
            raise ValueError(f"run config binding mismatch: {field}")
    if prompts["prompt_version"] != config["prompt_version"]:
        raise ValueError("prompt version mismatch")
    if policy["readiness_rule_version"] != config[
        "readiness_rule_version"
    ]:
        raise ValueError("readiness rule version mismatch")
    if tasks_doc["task_count"] != config["task_count"]:
        raise ValueError("task count mismatch")
    if config["development_repeats"] != 1:
        raise ValueError("development pilot must use one repeat")
    if config["tool_access"] != "disabled":
        raise ValueError("E2 policy pilot must disable tool access")
    if config["confirmatory_inference_allowed"] is not False:
        raise ValueError("development pilot cannot be confirmatory")
    contract_ids = {
        row["contract_id"] for row in contracts_doc["contracts"]
    }
    if any(
        task["contract_id"] not in contract_ids
        for task in tasks_doc["tasks"]
    ):
        raise ValueError("task references unknown contract")
    if output_schema["additionalProperties"] is not False:
        raise ValueError("output schema must reject additional properties")


def validate_execution_authorization(
    authorization: dict[str, Any],
    config: dict[str, Any],
) -> None:
    expected = {
        "decision": "authorized_to_execute_development_pilot",
        "run_config_id": config["run_config_id"],
        "dataset_id": config["dataset_id"],
        "authorized_task_count": config["task_count"],
        "authorized_repeats": config["development_repeats"],
        "endpoint": config["openai_base_url"],
        "model": config["model"],
        "tool_access": "disabled",
        "task_source_sha256": file_hash(TASKS_PATH),
        "prompt_sha256": file_hash(PROMPTS_PATH),
        "output_schema_sha256": file_hash(OUTPUT_SCHEMA_PATH),
        "run_config_sha256": file_hash(CONFIG_PATH),
        "runner_sha256": file_hash(Path(__file__)),
    }
    for field, value in expected.items():
        if authorization.get(field) != value:
            raise ValueError(
                f"execution authorization mismatch for {field}"
            )
    if authorization.get("confirmatory_inference_allowed") is not False:
        raise ValueError("development authorization cannot be confirmatory")
    if authorization.get("core_frozen") is not False:
        raise ValueError("development authorization cannot freeze the core")


def write_outputs(
    *,
    output_dir: Path,
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    config: dict[str, Any],
    adapter_configuration: dict[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    run_id = _run_id()
    snapshots = {
        TASKS_PATH: output_dir / "task_source_snapshot.json",
        CONTRACTS_PATH: output_dir / "contracts_snapshot.json",
        POLICY_PATH: output_dir / "policy_snapshot.json",
        PROMPTS_PATH: output_dir / "prompt_source_snapshot.json",
        OUTPUT_SCHEMA_PATH: output_dir / "output_schema_snapshot.json",
        CONFIG_PATH: output_dir / "run_config_snapshot.json",
        AUTHORIZATION_PATH: (
            output_dir / "execution_authorization_snapshot.json"
        ),
        Path(__file__): output_dir / "runner_source_snapshot.py",
    }
    for source, target in snapshots.items():
        shutil.copyfile(source, target)
    records_path = output_dir / "run_records.jsonl"
    with records_path.open("x", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(
                json.dumps({"run_id": run_id, **record}, ensure_ascii=False)
                + "\n"
            )
    report = {
        "schema_version": "1.0",
        "run_id": run_id,
        "run_config_id": config["run_config_id"],
        "dataset_id": config["dataset_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_bindings": {
            "task_source_sha256": file_hash(TASKS_PATH),
            "contracts_sha256": file_hash(CONTRACTS_PATH),
            "policy_sha256": file_hash(POLICY_PATH),
            "prompt_sha256": file_hash(PROMPTS_PATH),
            "output_schema_sha256": file_hash(OUTPUT_SCHEMA_PATH),
            "run_config_sha256": file_hash(CONFIG_PATH),
            "execution_authorization_sha256": file_hash(
                AUTHORIZATION_PATH
            ),
            "runner_sha256": file_hash(Path(__file__)),
        },
        "adapter_configuration": adapter_configuration,
        "summary": summary,
        "model_policy_revision_allowed": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    report_path = output_dir / "run_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    artifacts = list(snapshots.values()) + [records_path, report_path]
    manifest = {
        "schema_version": "1.0",
        "run_id": run_id,
        "artifacts": [
            {"filename": path.name, "sha256": file_hash(path)}
            for path in artifacts
        ],
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    (output_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def run_experiment(adapter) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tasks_doc = load_json(TASKS_PATH)
    contracts_doc = load_json(CONTRACTS_PATH)
    prompts = load_json(PROMPTS_PATH)
    output_schema = load_json(OUTPUT_SCHEMA_PATH)
    policy = load_json(POLICY_PATH)
    config = load_json(CONFIG_PATH)
    authorization = load_json(AUTHORIZATION_PATH)
    validate_inputs(
        tasks_doc,
        contracts_doc,
        prompts,
        output_schema,
        policy,
        config,
    )
    validate_execution_authorization(authorization, config)
    contracts = {
        row["tool_id"]: row for row in contracts_doc["contracts"]
    }
    records = [
        run_cell(
            task=task,
            contract=contracts[task["source_tool_id"]],
            prompts=prompts,
            output_schema=output_schema,
            config=config,
            adapter=adapter,
        )
        for task in tasks_doc["tasks"]
    ]
    supported_flags = [
        flag
        for flag in policy["flags"]
        if any(flag in task["expected_flags"] for task in tasks_doc["tasks"])
    ]
    return records, summarize(records, supported_flags)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    config = load_json(CONFIG_PATH)
    adapter = DeepSeekOpenAIAdapter.from_environment()
    adapter.timeout = float(config["timeout_seconds"])
    if adapter.model != config["model"]:
        raise RuntimeError("configured model mismatch")
    if adapter.base_url != config["openai_base_url"]:
        raise RuntimeError("configured base URL mismatch")
    if adapter.thinking != config["thinking"]:
        raise RuntimeError("configured thinking mismatch")
    adapter.ensure_ready()
    records, summary = run_experiment(adapter)
    report = write_outputs(
        output_dir=args.output_dir,
        records=records,
        summary=summary,
        config=config,
        adapter_configuration=adapter.configuration(),
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
