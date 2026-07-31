"""Run the E2 flags-only v1.1 development recheck."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import uuid
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
from core_freeze.e2_contract_boundaries.run_e2_development import (  # noqa: E402
    CONTRACTS_PATH,
    POLICY_PATH,
    TASKS_PATH,
    DeepSeekOpenAIAdapter,
    build_messages,
    file_hash,
    load_json,
    provider_call,
    summarize,
)


PROMPTS_PATH = HERE / "prompts_v1_1.json"
OUTPUT_SCHEMA_PATH = HERE / "output_schema_v1_1.json"
CONFIG_PATH = HERE / "run_config_development_v1_1.json"
AUTHORIZATION_PATH = (
    HERE / "execution_authorization_development_v1_1.json"
)


def _run_id() -> str:
    return f"E2-DEV-V11-RUN-{uuid.uuid4().hex[:16].upper()}"


def validate_flags_output(
    value: Any,
    output_schema: dict[str, Any],
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return False, ["output is not an object"]
    if set(value) != {"flags"}:
        errors.append("output keys must be exactly ['flags']")
    flags = value.get("flags")
    allowed_flags = set(
        output_schema["properties"]["flags"]["items"]["enum"]
    )
    if not isinstance(flags, list):
        errors.append("flags is not an array")
    else:
        if any(not isinstance(flag, str) for flag in flags):
            errors.append("flags contains non-string values")
        if len(flags) != len(set(flags)):
            errors.append("flags contains duplicates")
        unknown = {
            flag for flag in flags if isinstance(flag, str)
        } - allowed_flags
        if unknown:
            errors.append(f"unknown flags: {sorted(unknown)}")
    return not errors, errors


def derive_policy_decision(
    flags: list[str],
    policy: dict[str, Any],
) -> tuple[str, str]:
    flag_set = set(flags)
    for rule in policy["priority"]:
        relevant = set(rule["any_flags"])
        if (relevant and flag_set & relevant) or (
            not relevant and not flag_set
        ):
            return rule["primary_status"], rule["policy_expected_action"]
    raise ValueError(f"no policy decision for flags: {flags}")


def score_flags_prediction(
    parsed: Any,
    task: dict[str, Any],
    output_schema: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    valid, errors = validate_flags_output(parsed, output_schema)
    if not valid:
        return {
            "schema_valid": False,
            "schema_errors": errors,
            "predicted_flags": None,
            "predicted_primary_status": None,
            "predicted_action": None,
            "decision_source": "not_derived_invalid_flags",
            "flags_exact": False,
            "flags_jaccard": 0.0,
            "primary_status_correct": False,
            "action_correct": False,
        }
    predicted_flags = parsed["flags"]
    primary_status, action = derive_policy_decision(
        predicted_flags,
        policy,
    )
    expected = set(task["expected_flags"])
    predicted = set(predicted_flags)
    union = expected | predicted
    return {
        "schema_valid": True,
        "schema_errors": [],
        "predicted_flags": predicted_flags,
        "predicted_primary_status": primary_status,
        "predicted_action": action,
        "decision_source": "deterministic_policy_from_predicted_flags",
        "flags_exact": predicted == expected,
        "flags_jaccard": (
            len(predicted & expected) / len(union) if union else 1.0
        ),
        "primary_status_correct": (
            primary_status == task["primary_status"]
        ),
        "action_correct": action == task["policy_expected_action"],
    }


def run_cell(
    *,
    task: dict[str, Any],
    contract: dict[str, Any],
    prompts: dict[str, Any],
    output_schema: dict[str, Any],
    policy: dict[str, Any],
    config: dict[str, Any],
    adapter,
) -> dict[str, Any]:
    started = time.perf_counter()
    messages = build_messages(task, contract, prompts)
    response, attempts, error = provider_call(adapter, messages, config)
    raw_output = ""
    parsed_output = None
    parse_status = "provider_error"
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
    scoring = score_flags_prediction(
        parsed_output,
        task,
        output_schema,
        policy,
    )
    return {
        "cell_id": f"{task['task_id']}::flags_only_policy::R1",
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
        "condition": "flags_only_deterministic_policy",
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


def validate_inputs(
    tasks_doc: dict[str, Any],
    contracts_doc: dict[str, Any],
    prompts: dict[str, Any],
    output_schema: dict[str, Any],
    policy: dict[str, Any],
    config: dict[str, Any],
) -> None:
    expected_bindings = {
        "dataset_id": tasks_doc["dataset_id"],
        "task_source_sha256": file_hash(TASKS_PATH),
        "contracts_sha256": file_hash(CONTRACTS_PATH),
        "policy_sha256": file_hash(POLICY_PATH),
        "prompt_sha256": file_hash(PROMPTS_PATH),
        "output_schema_sha256": file_hash(OUTPUT_SCHEMA_PATH),
    }
    for field, expected in expected_bindings.items():
        if config.get(field) != expected:
            raise ValueError(f"run config binding mismatch: {field}")
    if prompts["prompt_version"] != config["prompt_version"]:
        raise ValueError("prompt version mismatch")
    if policy["readiness_rule_version"] != config[
        "readiness_rule_version"
    ]:
        raise ValueError("readiness policy mismatch")
    if tasks_doc["task_count"] != config["task_count"]:
        raise ValueError("task count mismatch")
    if config["development_repeats"] != 1:
        raise ValueError("development recheck must use one repeat")
    if config["tool_access"] != "disabled":
        raise ValueError("E2 policy recheck must disable tool access")
    if config["confirmatory_inference_allowed"] is not False:
        raise ValueError("development recheck cannot be confirmatory")
    if config["model_policy_revision_allowed_after_open"] is not False:
        raise ValueError("opened development version must remain immutable")
    if set(output_schema["required"]) != {"flags"}:
        raise ValueError("v1.1 output must require only flags")
    if set(output_schema["properties"]) != {"flags"}:
        raise ValueError("v1.1 output must expose only flags")
    if output_schema["additionalProperties"] is not False:
        raise ValueError("v1.1 output must reject extra fields")
    if "primary_status" in prompts["output_contract"]:
        raise ValueError("model output contract must not expose primary_status")
    if "action" in prompts["output_contract"]:
        raise ValueError("model output contract must not expose action")
    contract_ids = {
        row["contract_id"] for row in contracts_doc["contracts"]
    }
    if any(
        task["contract_id"] not in contract_ids
        for task in tasks_doc["tasks"]
    ):
        raise ValueError("task references unknown contract")


def expected_authorization(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision": "authorized_to_execute_v1_1_development_recheck",
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


def validate_execution_authorization(
    authorization: dict[str, Any],
    config: dict[str, Any],
) -> None:
    for field, expected in expected_authorization(config).items():
        if authorization.get(field) != expected:
            raise ValueError(
                f"execution authorization mismatch for {field}"
            )
    if authorization.get("external_data_sharing_authorized") is not True:
        raise ValueError("external data sharing is not authorized")
    if authorization.get("confirmatory_inference_allowed") is not False:
        raise ValueError("development recheck cannot be confirmatory")
    if authorization.get("core_frozen") is not False:
        raise ValueError("development authorization cannot freeze core")


def execute_tasks(
    adapter,
    *,
    tasks_doc: dict[str, Any],
    contracts_doc: dict[str, Any],
    prompts: dict[str, Any],
    output_schema: dict[str, Any],
    policy: dict[str, Any],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    contracts = {
        row["tool_id"]: row for row in contracts_doc["contracts"]
    }
    records = [
        run_cell(
            task=task,
            contract=contracts[task["source_tool_id"]],
            prompts=prompts,
            output_schema=output_schema,
            policy=policy,
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
    summary = summarize(records, supported_flags)
    return records, {
        **summary,
        "model_output_fields": ["flags"],
        "primary_status_source": (
            "deterministic_policy_from_predicted_flags"
        ),
        "action_source": "deterministic_policy_from_predicted_flags",
    }


def run_experiment(adapter) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not AUTHORIZATION_PATH.exists():
        raise FileNotFoundError(
            "v1.1 execution authorization is pending"
        )
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
    return execute_tasks(
        adapter,
        tasks_doc=tasks_doc,
        contracts_doc=contracts_doc,
        prompts=prompts,
        output_schema=output_schema,
        policy=policy,
        config=config,
    )


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
        "schema_version": "1.1",
        "run_id": run_id,
        "run_config_id": config["run_config_id"],
        "dataset_id": config["dataset_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_bindings": {
            **expected_authorization(config),
            "execution_authorization_sha256": file_hash(
                AUTHORIZATION_PATH
            ),
        },
        "adapter_configuration": adapter_configuration,
        "summary": summary,
        "model_policy_revision_allowed_after_open": False,
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
        "schema_version": "1.1",
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
