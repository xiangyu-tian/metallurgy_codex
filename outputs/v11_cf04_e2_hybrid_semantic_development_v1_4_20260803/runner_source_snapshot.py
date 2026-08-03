"""Run an authorized E2 hybrid semantic-layer development recheck."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import uuid
from collections import Counter
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
from core_freeze.e2_contract_boundaries.hybrid_gate_v1 import (  # noqa: E402
    derive_structural_flags,
    run_hybrid_gate,
    validate_semantic_output,
)
from core_freeze.e2_contract_boundaries.run_e2_development import (  # noqa: E402
    DeepSeekOpenAIAdapter,
    contract_view,
    file_hash,
    load_json,
    provider_call,
)


TASKS_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_pilot_v2_observable_candidate_20260731"
    / "e2_pilot_tasks_v2.json"
)
VALIDATION_TASKS_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_independent_validation_v1_candidate_20260731"
    / "e2_validation_tasks_v1.json"
)
CONTRACTS_PATH = HERE.parent / "verified_core" / "contracts_v1.json"
BASE_POLICY_PATH = HERE / "policy_v1.json"
HYBRID_POLICY_PATH = HERE / "hybrid_gate_policy_v1.json"
PROMPTS_PATH = HERE / "prompts_hybrid_semantic_v1_4.json"
OUTPUT_SCHEMA_PATH = HERE / "output_schema_hybrid_semantic_v1.json"
CONFIG_PATH = HERE / "run_config_hybrid_semantic_development_v1_4.json"
ADVANCEMENT_GATE_PATH = (
    HERE / "hybrid_semantic_development_gate_v1.json"
)
AUTHORIZATION_REQUEST_PATH = (
    HERE / "execution_authorization_request_hybrid_semantic_v1_4.json"
)
AUTHORIZATION_PATH = (
    HERE
    / "execution_authorization_hybrid_semantic_development_v1_4.json"
)


def _run_id() -> str:
    return f"E2-HYBRID-SEMANTIC-DEV-{uuid.uuid4().hex[:16].upper()}"


def expected_semantic_flags(
    task: dict[str, Any],
    hybrid_policy: dict[str, Any],
) -> list[str]:
    allowed = set(hybrid_policy["semantic_flags"])
    return [
        flag
        for flag in hybrid_policy["flag_order"]
        if flag in allowed and flag in task["expected_flags"]
    ]


def _ambiguous_parameter_paths(
    value: Any,
    path: str = "parameters",
) -> list[str]:
    if isinstance(value, dict):
        candidates = value.get("candidates")
        if (
            value.get("status") == "ambiguous"
            and isinstance(candidates, list)
            and candidates
        ):
            return [path]
        paths: list[str] = []
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            paths.extend(_ambiguous_parameter_paths(item, child))
        return paths
    if isinstance(value, list):
        paths = []
        for index, item in enumerate(value):
            paths.extend(
                _ambiguous_parameter_paths(item, f"{path}[{index}]")
            )
        return paths
    return []


def _explicit_count_evidence(
    request_context: dict[str, Any],
    verification_scope: dict[str, Any],
    field: str,
) -> dict[str, Any]:
    requested = request_context.get(field)
    contract_field = field.removeprefix("requested_")
    expected = verification_scope.get(contract_field)
    if requested is None:
        status = "not_provided"
    elif expected is None:
        status = "contract_unspecified"
    elif requested == expected:
        status = "matches_contract"
    else:
        status = "mismatches_contract"
    return {
        "status": status,
        "requested": requested,
        "contract_expected": expected,
    }


def build_semantic_request_view(
    task: dict[str, Any],
    contract: dict[str, Any],
    hybrid_policy: dict[str, Any],
) -> dict[str, Any]:
    structured_state = task["structured_state"]
    parameters = structured_state.get("parameters")
    if not isinstance(parameters, dict):
        parameters = {}
    request_context = structured_state.get("request_context")
    if not isinstance(request_context, dict):
        request_context = {}
    verification_scope = contract.get("verification_scope")
    if not isinstance(verification_scope, dict):
        verification_scope = {}
    requested_system = request_context.get("requested_system")
    supported_systems = list(contract.get("supported_systems") or [])
    if requested_system is None:
        system_status = "not_provided"
    elif requested_system in supported_systems:
        system_status = "supported"
    else:
        system_status = "unsupported"
    return {
        "structured_state": structured_state,
        "deterministic_context": {
            "structural_flags": derive_structural_flags(
                structured_state,
                contract,
                hybrid_policy,
            ),
            "missing_required_inputs": [
                field
                for field in contract["required_inputs"]
                if field not in parameters
            ],
            "ambiguous_parameter_paths": _ambiguous_parameter_paths(
                parameters
            ),
            "explicit_domain_evidence": {
                "requested_system": {
                    "status": system_status,
                    "requested": requested_system,
                    "contract_supported": supported_systems,
                },
                "requested_phase_count": _explicit_count_evidence(
                    request_context,
                    verification_scope,
                    "requested_phase_count",
                ),
                "requested_component_count": _explicit_count_evidence(
                    request_context,
                    verification_scope,
                    "requested_component_count",
                ),
            },
            "parameter_field_count_is_domain_count": False,
        },
    }


def build_semantic_messages(
    task: dict[str, Any],
    contract: dict[str, Any],
    prompts: dict[str, Any],
    hybrid_policy: dict[str, Any],
) -> list[dict[str, str]]:
    contract_json = json.dumps(
        contract_view(contract),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    request_json = json.dumps(
        build_semantic_request_view(task, contract, hybrid_policy),
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


def score_semantic_prediction(
    parsed: Any,
    task: dict[str, Any],
    contract: dict[str, Any],
    output_schema: dict[str, Any],
    base_policy: dict[str, Any],
    hybrid_policy: dict[str, Any],
) -> dict[str, Any]:
    valid, errors = validate_semantic_output(parsed, output_schema)
    expected_semantic = expected_semantic_flags(task, hybrid_policy)
    structural_flags = derive_structural_flags(
        task["structured_state"],
        contract,
        hybrid_policy,
    )
    structural_allowed = set(hybrid_policy["structural_flags"])
    expected_structural = [
        flag
        for flag in hybrid_policy["flag_order"]
        if flag in structural_allowed and flag in task["expected_flags"]
    ]
    structural_exact = (
        set(structural_flags) == set(expected_structural)
    )
    if not valid:
        return {
            "semantic_schema_valid": False,
            "semantic_schema_errors": errors,
            "expected_structural_flags": expected_structural,
            "structural_flags": structural_flags,
            "structural_flags_exact": structural_exact,
            "expected_semantic_flags": expected_semantic,
            "predicted_semantic_flags": None,
            "semantic_flags_exact": False,
            "semantic_flags_jaccard": 0.0,
            "merged_flags": None,
            "merged_flags_exact": False,
            "predicted_primary_status": None,
            "predicted_action": None,
            "action_correct": False,
        }
    result = run_hybrid_gate(
        structured_state=task["structured_state"],
        contract=contract,
        semantic_output=parsed,
        base_policy=base_policy,
        hybrid_policy=hybrid_policy,
        semantic_schema=output_schema,
    )
    predicted_semantic = result["semantic_flags"]
    semantic_union = set(expected_semantic) | set(predicted_semantic)
    return {
        "semantic_schema_valid": True,
        "semantic_schema_errors": [],
        "expected_structural_flags": expected_structural,
        "structural_flags": structural_flags,
        "structural_flags_exact": structural_exact,
        "expected_semantic_flags": expected_semantic,
        "predicted_semantic_flags": predicted_semantic,
        "semantic_flags_exact": (
            set(predicted_semantic) == set(expected_semantic)
        ),
        "semantic_flags_jaccard": (
            len(set(predicted_semantic) & set(expected_semantic))
            / len(semantic_union)
            if semantic_union
            else 1.0
        ),
        "merged_flags": result["merged_flags"],
        "merged_flags_exact": (
            set(result["merged_flags"]) == set(task["expected_flags"])
        ),
        "predicted_primary_status": result["primary_status"],
        "predicted_action": result["policy_expected_action"],
        "action_correct": (
            result["policy_expected_action"]
            == task["policy_expected_action"]
        ),
    }


def run_cell(
    *,
    task: dict[str, Any],
    contract: dict[str, Any],
    prompts: dict[str, Any],
    output_schema: dict[str, Any],
    base_policy: dict[str, Any],
    hybrid_policy: dict[str, Any],
    config: dict[str, Any],
    adapter,
) -> dict[str, Any]:
    started = time.perf_counter()
    messages = build_semantic_messages(
        task,
        contract,
        prompts,
        hybrid_policy,
    )
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
    scoring = score_semantic_prediction(
        parsed_output,
        task,
        contract,
        output_schema,
        base_policy,
        hybrid_policy,
    )
    return {
        "cell_id": f"{task['task_id']}::hybrid_semantic::R1",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "task_id": task["task_id"],
        "base_task_id": task["base_task_id"],
        "base_task_group_id": task["base_task_group_id"],
        "source_tool_id": task["source_tool_id"],
        "contract_id": task["contract_id"],
        "contract_hash": task["contract_hash"],
        "mutation_types": task["mutation_types"],
        "expected_flags": task["expected_flags"],
        "expected_action": task["policy_expected_action"],
        "condition": "deterministic_structural_plus_llm_semantic",
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
    base_policy: dict[str, Any],
    hybrid_policy: dict[str, Any],
    config: dict[str, Any],
) -> None:
    expected_bindings = {
        "dataset_id": tasks_doc["dataset_id"],
        "task_source_sha256": file_hash(TASKS_PATH),
        "contracts_sha256": file_hash(CONTRACTS_PATH),
        "base_policy_sha256": file_hash(BASE_POLICY_PATH),
        "hybrid_policy_sha256": file_hash(HYBRID_POLICY_PATH),
        "prompt_sha256": file_hash(PROMPTS_PATH),
        "output_schema_sha256": file_hash(OUTPUT_SCHEMA_PATH),
        "advancement_gate_sha256": file_hash(
            ADVANCEMENT_GATE_PATH
        ),
    }
    for field, expected in expected_bindings.items():
        if config.get(field) != expected:
            raise ValueError(f"run config binding mismatch: {field}")
    if prompts["prompt_version"] != config["prompt_version"]:
        raise ValueError("prompt version mismatch")
    if tasks_doc["task_count"] != config["task_count"]:
        raise ValueError("task count mismatch")
    if config["development_repeats"] != 1:
        raise ValueError("development recheck must use one repeat")
    if config["tool_access"] != "disabled":
        raise ValueError("hybrid semantic recheck must disable tool access")
    if config["validation_dataset_access"] != "forbidden":
        raise ValueError("development runner cannot access validation data")
    if config["model_policy_revision_allowed_after_open"] is not False:
        raise ValueError("opened development version must be immutable")
    if config["confirmatory_inference_allowed"] is not False:
        raise ValueError("development recheck cannot be confirmatory")
    if set(output_schema["required"]) != {"semantic_flags"}:
        raise ValueError("semantic output must require semantic_flags")
    if set(output_schema["properties"]) != {"semantic_flags"}:
        raise ValueError("semantic output exposes forbidden fields")
    if set(hybrid_policy["structural_flags"]) & set(
        hybrid_policy["semantic_flags"]
    ):
        raise ValueError("hybrid responsibility sets overlap")
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
        "decision": "authorized_to_execute_hybrid_semantic_development_v1_4",
        "run_config_id": config["run_config_id"],
        "dataset_id": config["dataset_id"],
        "authorized_task_count": config["task_count"],
        "authorized_repeats": config["development_repeats"],
        "endpoint": config["openai_base_url"],
        "model": config["model"],
        "tool_access": "disabled",
        "validation_dataset_access": "forbidden",
        "task_source_sha256": file_hash(TASKS_PATH),
        "prompt_sha256": file_hash(PROMPTS_PATH),
        "output_schema_sha256": file_hash(OUTPUT_SCHEMA_PATH),
        "run_config_sha256": file_hash(CONFIG_PATH),
        "runner_sha256": file_hash(Path(__file__)),
        "advancement_gate_sha256": file_hash(
            ADVANCEMENT_GATE_PATH
        ),
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


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in records if row["status"] == "completed"]
    supported_flags = (
        "contract_defined_out_of_domain",
        "contract_defined_unsupported_system",
    )
    by_flag = {}
    for flag in supported_flags:
        true_positive = sum(
            flag in row["expected_semantic_flags"]
            and flag in (row["predicted_semantic_flags"] or [])
            for row in completed
        )
        false_positive = sum(
            flag not in row["expected_semantic_flags"]
            and flag in (row["predicted_semantic_flags"] or [])
            for row in completed
        )
        false_negative = sum(
            flag in row["expected_semantic_flags"]
            and flag not in (row["predicted_semantic_flags"] or [])
            for row in completed
        )
        denominator = 2 * true_positive + false_positive + false_negative
        by_flag[flag] = {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "f1": (
                2 * true_positive / denominator
                if denominator
                else None
            ),
        }
    f1_values = [
        row["f1"] for row in by_flag.values() if row["f1"] is not None
    ]
    return {
        "status": (
            "completed"
            if len(completed) == len(records)
            else "completed_with_provider_failures"
        ),
        "cell_count": len(records),
        "completed_count": len(completed),
        "provider_failure_count": sum(
            row["status"] == "provider_error" for row in records
        ),
        "retried_cell_count": sum(
            row["provider_attempt_count"] > 1 for row in records
        ),
        "semantic_schema_valid_rate": (
            sum(row["semantic_schema_valid"] for row in completed)
            / len(completed)
            if completed
            else None
        ),
        "semantic_schema_valid_count": sum(
            row["semantic_schema_valid"] for row in completed
        ),
        "structural_flags_exact_count": sum(
            row["structural_flags_exact"] for row in records
        ),
        "structural_flags_exact_accuracy": (
            sum(row["structural_flags_exact"] for row in records)
            / len(records)
            if records
            else None
        ),
        "semantic_flags_exact_accuracy": (
            sum(row["semantic_flags_exact"] for row in completed)
            / len(completed)
            if completed
            else None
        ),
        "mean_semantic_flags_jaccard": (
            sum(row["semantic_flags_jaccard"] for row in completed)
            / len(completed)
            if completed
            else None
        ),
        "semantic_supported_flag_macro_f1": (
            sum(f1_values) / len(f1_values) if f1_values else None
        ),
        "semantic_flag_metrics": by_flag,
        "merged_flags_exact_accuracy": (
            sum(row["merged_flags_exact"] for row in completed)
            / len(completed)
            if completed
            else None
        ),
        "merged_flags_exact_count": sum(
            row["merged_flags_exact"] for row in completed
        ),
        "action_accuracy": (
            sum(row["action_correct"] for row in completed)
            / len(completed)
            if completed
            else None
        ),
        "action_correct_count": sum(
            row["action_correct"] for row in completed
        ),
        "premature_call_count": sum(
            row["expected_action"] != "call"
            and row["predicted_action"] == "call"
            for row in completed
        ),
        "predicted_action_counts": dict(
            sorted(
                Counter(
                    row["predicted_action"] or "__INVALID__"
                    for row in completed
                ).items()
            )
        ),
        "model_output_fields": ["semantic_flags"],
        "structural_flags_source": "deterministic_checker",
        "decision_source": "frozen_policy_after_flag_merge",
    }


def execute_tasks(
    adapter,
    *,
    tasks_doc: dict[str, Any],
    contracts_doc: dict[str, Any],
    prompts: dict[str, Any],
    output_schema: dict[str, Any],
    base_policy: dict[str, Any],
    hybrid_policy: dict[str, Any],
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
            base_policy=base_policy,
            hybrid_policy=hybrid_policy,
            config=config,
            adapter=adapter,
        )
        for task in tasks_doc["tasks"]
    ]
    return records, summarize(records)


def run_experiment(adapter) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not AUTHORIZATION_PATH.exists():
        raise FileNotFoundError(
            "hybrid semantic execution authorization is pending"
        )
    tasks_doc = load_json(TASKS_PATH)
    contracts_doc = load_json(CONTRACTS_PATH)
    prompts = load_json(PROMPTS_PATH)
    output_schema = load_json(OUTPUT_SCHEMA_PATH)
    base_policy = load_json(BASE_POLICY_PATH)
    hybrid_policy = load_json(HYBRID_POLICY_PATH)
    config = load_json(CONFIG_PATH)
    authorization = load_json(AUTHORIZATION_PATH)
    validate_inputs(
        tasks_doc,
        contracts_doc,
        prompts,
        output_schema,
        base_policy,
        hybrid_policy,
        config,
    )
    validate_execution_authorization(authorization, config)
    return execute_tasks(
        adapter,
        tasks_doc=tasks_doc,
        contracts_doc=contracts_doc,
        prompts=prompts,
        output_schema=output_schema,
        base_policy=base_policy,
        hybrid_policy=hybrid_policy,
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
        BASE_POLICY_PATH: output_dir / "base_policy_snapshot.json",
        HYBRID_POLICY_PATH: output_dir / "hybrid_policy_snapshot.json",
        ADVANCEMENT_GATE_PATH: (
            output_dir / "advancement_gate_snapshot.json"
        ),
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
        "schema_version": "1.0-development",
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
        "validation_dataset_access": "forbidden",
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
        "schema_version": "1.0-development",
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
    if not AUTHORIZATION_PATH.exists():
        raise FileNotFoundError(
            "hybrid semantic execution authorization is pending"
        )
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
