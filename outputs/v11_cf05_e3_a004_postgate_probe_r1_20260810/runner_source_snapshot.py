"""Execute exactly ten authorized A004 post-gate probe requests without tool execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
TOOLS_DIR = WORKSPACE / "Tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from models_core.llm_adapters import DeepSeekOpenAIAdapter, LLMAdapterError  # noqa: E402
from Tools.core_freeze.e3_routing import a004_contract_adjudication as gate  # noqa: E402


CONFIG_PATH = Path(__file__).with_name("a004_postgate_probe_runtime_config_v1.json")
EXPECTED_RUN_ID = "V11-CF05-E3-A004-POSTGATE-PROBE-R1-20260810"
EXPECTED_OPENING_ID = "V11-CF05-E3-A004-POSTGATE-PROBE-OPENING-V1-20260810"
EXPECTED_DECISION = "authorized_to_execute_a004_postgate_probe_r1"
EXPECTED_TOOL_IDS = ["E3C014", "E3C027", "A004", "E3C005", "B022"]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def write_json_atomic(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    gate.write_json(temporary, value)
    temporary.replace(path)


def validate_opening(config: dict[str, Any]) -> dict[str, Any]:
    if config["run_id"] != EXPECTED_RUN_ID or config["opening_id"] != EXPECTED_OPENING_ID:
        raise ValueError("unexpected runtime identity")
    if config["scheduled_request_count"] != 10:
        raise ValueError("scheduled request count changed")
    if config["provider_max_attempts"] != 1 or config["provider_retry_allowed"] is not False:
        raise ValueError("runtime must remain one-shot without retry")
    for field in ("tool_execution_allowed", "independent_validation_claim_allowed",
                  "confirmatory_inference_allowed", "core_frozen"):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")
    paths = {name: gate.validate_binding(binding) for name, binding in config["bindings"].items()}
    documents = {name: gate.load_json(path) for name, path in paths.items()
                 if path.suffix.lower() == ".json"}
    opening_dir = paths["opening_manifest"].parent
    manifest = documents["opening_manifest"]
    manifest_rows = {row["filename"]: row for row in manifest["artifacts"]}
    if len(manifest_rows) != manifest["artifact_count"]:
        raise ValueError("opening manifest contains duplicate artifacts")
    for filename, row in manifest_rows.items():
        artifact = opening_dir / filename
        if not artifact.is_file() or gate.file_hash(artifact) != row["sha256"]:
            raise ValueError(f"opening artifact hash mismatch: {filename}")
    tasks = documents["input_tasks"]["tasks"]
    cells = documents["run_cells"]["cells"]
    schema_view = documents["schema_view"]
    if len(tasks) != 10 or len(cells) != 10 or len({row["cell_id"] for row in cells}) != 10:
        raise ValueError("opening dimensions changed")
    if schema_view["ordered_candidate_tool_ids"] != EXPECTED_TOOL_IDS:
        raise ValueError("frozen schema order changed")
    if [tool["function"]["name"] for tool in schema_view["openai_tools"]] != EXPECTED_TOOL_IDS:
        raise ValueError("schema body and ordered ids differ")
    if any(cell["model_run_repeat"] != 1 or cell["provider_max_attempts"] != 1 for cell in cells):
        raise ValueError("run cells must remain one-shot R1")
    task_by_id = {row["task_id"]: row for row in tasks}
    if len(task_by_id) != 10 or any(cell["task_id"] not in task_by_id for cell in cells):
        raise ValueError("task/cell identifiers changed")
    profiles = gate.load_bound_profile_registry(documents["contract_gate_config"])
    return {"paths": paths, "documents": documents, "tasks": tasks, "cells": cells,
            "task_by_id": task_by_id, "schema_view": schema_view,
            "prompt": documents["selector_prompt"], "profiles": profiles}


def validate_authorization(authorization: dict[str, Any], config: dict[str, Any],
                           opening: dict[str, Any]) -> None:
    expected = {
        "run_id": EXPECTED_RUN_ID,
        "opening_id": EXPECTED_OPENING_ID,
        "decision": EXPECTED_DECISION,
        "provider": config["provider"],
        "endpoint": config["openai_base_url"],
        "model": config["model"],
        "scheduled_request_count": 10,
        "opening_manifest_sha256": gate.file_hash(opening["paths"]["opening_manifest"]),
        "runtime_config_sha256": gate.file_hash(CONFIG_PATH),
        "runner_sha256": gate.file_hash(Path(__file__)),
    }
    for field, value in expected.items():
        if authorization.get(field) != value:
            raise ValueError(f"execution authorization mismatch for {field}")
    policies = {
        "external_data_sharing_authorized": True,
        "external_api_execution_authorized": True,
        "tool_execution_authorized": False,
        "provider_retry_authorized": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    for field, value in policies.items():
        if authorization.get(field) is not value:
            raise ValueError(f"authorization policy mismatch for {field}")
    for field in ("authorized_by", "authorized_at", "authorization_basis", "runner_git_commit"):
        if not isinstance(authorization.get(field), str) or not authorization[field].strip():
            raise ValueError(f"authorization missing {field}")
    parsed = datetime.fromisoformat(authorization["authorized_at"])
    if parsed.tzinfo is None:
        raise ValueError("authorized_at must include timezone")


def payload_for(cell: dict[str, Any], opening: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": opening["prompt"]["system"]},
            {"role": "user", "content": opening["task_by_id"][cell["task_id"]]["problem_text"]},
        ],
        "tools": opening["schema_view"]["openai_tools"],
        "tool_choice": config["tool_choice"], "temperature": config["temperature"],
        "max_tokens": config["max_tokens"], "stream": False,
        "thinking": {"type": config["thinking"]},
    }


def response_message(response: Any) -> dict[str, Any] | None:
    if not isinstance(response, dict) or not isinstance(response.get("choices"), list) or not response["choices"]:
        return None
    message = response["choices"][0].get("message")
    return message if isinstance(message, dict) else None


def raw_summary(response: Any) -> dict[str, Any]:
    calls = gate.parse_calls(response)
    return {
        "response_shape_valid": response_message(response) is not None,
        "tool_call_count": len(calls),
        "called_tool_ids": [row["tool_id"] for row in calls],
        "all_arguments_json_valid": bool(calls) and all(row["arguments_json_valid"] for row in calls),
        "exactly_one_tool_call": len(calls) == 1,
    }


def execute(config: dict[str, Any], opening: dict[str, Any], authorization: dict[str, Any],
            adapter: DeepSeekOpenAIAdapter, checkpoint_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    adapter.ensure_ready()
    if (adapter.base_url != config["openai_base_url"] or adapter.model != config["model"]
            or adapter.thinking != config["thinking"]):
        raise ValueError("adapter endpoint, model, or thinking differs from frozen runtime")
    adapter.timeout = float(config["timeout_seconds"])
    raw_rows: list[dict[str, Any]] = []
    gate_rows: list[dict[str, Any]] = []
    for index, cell in enumerate(opening["cells"], start=1):
        payload = payload_for(cell, opening, config)
        started_at = datetime.now().astimezone().isoformat()
        started = time.perf_counter()
        response, provider_error = None, None
        try:
            response = adapter.transport(
                f"{adapter.base_url}/chat/completions",
                {"Content-Type": "application/json; charset=utf-8",
                 "Authorization": f"Bearer {adapter.api_key}"},
                payload, adapter.timeout,
            )
        except LLMAdapterError as exc:
            provider_error = str(exc)
        summary = raw_summary(response)
        raw_row = {
            "cell_id": cell["cell_id"], "task_id": cell["task_id"],
            "model_run_repeat": 1, "request_body_sha256": json_hash(payload),
            "started_at": started_at,
            "api_latency_ms": round((time.perf_counter() - started) * 1000.0, 6),
            "transport_accepted": response_message(response) is not None,
            "provider_error": provider_error, "response_id": response.get("id") if isinstance(response, dict) else None,
            "response_model": response.get("model") if isinstance(response, dict) else None,
            "usage": response.get("usage") if isinstance(response, dict) else None,
            **summary, "raw_response": response, "tool_executed": False, "retry_count": 0,
        }
        decision = gate.adjudicate(
            opening["task_by_id"][cell["task_id"]]["problem_text"], response, opening["profiles"]
        )
        gate_row = {
            "cell_id": cell["cell_id"], "task_id": cell["task_id"],
            "raw_result_sha256": json_hash(raw_row), "gate_decision": decision,
            "raw_response_modified": False, "tool_executed": False,
        }
        raw_rows.append(raw_row)
        gate_rows.append(gate_row)
        write_json_atomic(checkpoint_path, {
            "schema_version": "1.0", "run_id": EXPECTED_RUN_ID,
            "authorization_content_sha256": json_hash(authorization),
            "completed_count": len(raw_rows), "raw_results": raw_rows, "gate_results": gate_rows,
        })
        print(json.dumps({"progress": f"{index}/10", "cell_id": cell["cell_id"],
                          "accepted": raw_row["transport_accepted"],
                          "raw_called_tool_ids": raw_row["called_tool_ids"],
                          "gate_decision": decision["decision"],
                          "gate_selected_tool_id": decision["selected_tool_id"]}, ensure_ascii=False), flush=True)
    return raw_rows, gate_rows


def build_outputs(authorization_path: Path, output_dir: Path,
                  adapter: DeepSeekOpenAIAdapter) -> dict[str, Any]:
    config = gate.load_json(CONFIG_PATH)
    opening = validate_opening(config)
    authorization = gate.load_json(authorization_path)
    validate_authorization(authorization, config, opening)
    if output_dir.exists() and (output_dir / "artifact_manifest.json").exists():
        raise FileExistsError("completed post-gate probe output already exists")
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = output_dir / "a004_postgate_probe.checkpoint.json"
    raw_rows, gate_rows = execute(config, opening, authorization, adapter, checkpoint)
    gate.write_json(output_dir / "a004_postgate_raw_results.json", {
        "schema_version": "1.0", "run_id": EXPECTED_RUN_ID, "result_count": len(raw_rows),
        "results": raw_rows,
    })
    gate.write_json(output_dir / "a004_postgate_gate_results.json", {
        "schema_version": "1.0", "run_id": EXPECTED_RUN_ID, "result_count": len(gate_rows),
        "results": gate_rows,
    })
    report = {
        "schema_version": "1.0", "run_id": EXPECTED_RUN_ID, "opening_id": EXPECTED_OPENING_ID,
        "run_status": "development_probe_complete_pending_offline_scoring",
        "provider": config["provider"], "model": config["model"],
        "scheduled_request_count": 10, "external_api_calls": 10,
        "transport_accepted_count": sum(row["transport_accepted"] for row in raw_rows),
        "raw_exactly_one_call_count": sum(row["exactly_one_tool_call"] for row in raw_rows),
        "raw_structure_violation_count": sum(row["tool_call_count"] != 1 for row in raw_rows),
        "gate_allow_original_count": sum(row["gate_decision"]["decision"] == "allow_original_single_call" for row in gate_rows),
        "gate_allow_adjudicated_count": sum(row["gate_decision"]["decision"] == "allow_adjudicated_single_call" for row in gate_rows),
        "gate_review_required_count": sum(row["gate_decision"]["decision"] == "review_required" for row in gate_rows),
        "provider_error_count": sum(row["provider_error"] is not None for row in raw_rows),
        "tool_calls_executed": 0, "retries_executed": 0,
        "raw_responses_modified": False, "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress", "core_frozen": False,
    }
    gate.write_json(output_dir / "a004_postgate_runtime_report.json", report)
    for filename, source in {
        "a004_postgate_runtime_config_snapshot.json": CONFIG_PATH,
        "execution_authorization_snapshot.json": authorization_path,
        "runner_source_snapshot.py": Path(__file__),
    }.items():
        shutil.copyfile(source, output_dir / filename)
    checkpoint.unlink(missing_ok=True)
    artifact_paths = [path for path in output_dir.iterdir()
                      if path.is_file() and path.name != "artifact_manifest.json"]
    gate.write_json(output_dir / "artifact_manifest.json", {
        "schema_version": "1.0", "run_id": EXPECTED_RUN_ID,
        "artifact_count": len(artifact_paths),
        "artifacts": [{"filename": path.name, "sha256": gate.file_hash(path), "bytes": path.stat().st_size}
                      for path in sorted(artifact_paths, key=lambda item: item.name)],
    })
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-authorization", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = build_outputs(args.execution_authorization.resolve(), args.output_dir.resolve(),
                           DeepSeekOpenAIAdapter.from_environment())
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
