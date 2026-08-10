"""Execute the explicitly authorized 64-cell E3 multi-target development run."""

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


CONFIG_PATH = Path(__file__).with_name("multitarget_runtime_config_v1.json")
EXPECTED_OPENING_ID = "V11-CF05-E3-MULTITARGET-MIXED-OPENING-V1-20260810"
EXPECTED_RUN_ID = "V11-CF05-E3-MULTITARGET-MIXED-R1-20260810"
EXPECTED_DECISION = "authorized_to_execute_multitarget_mixed_development"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_json_atomic(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    write_json(temporary, value)
    temporary.replace(path)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_binding(binding: dict[str, str]) -> Path:
    path = WORKSPACE / binding["path"]
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = file_hash(path)
    if actual != binding["sha256"].lower():
        raise ValueError(f"bound file hash mismatch for {path}: {actual}")
    return path


def payload_for(
    cell: dict[str, Any],
    task_by_id: dict[str, dict[str, Any]],
    view_by_id: dict[str, dict[str, Any]],
    prompt: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    task = task_by_id[cell["task_id"]]
    view = view_by_id[cell["candidate_view_id"]]
    return {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": task["problem_text"]},
        ],
        "tools": view["openai_tools"],
        "tool_choice": config["tool_choice"],
        "temperature": config["temperature"],
        "max_tokens": config["max_tokens"],
        "stream": False,
        "thinking": {"type": config["thinking"]},
    }


def validate_opening(config: dict[str, Any]) -> dict[str, Any]:
    if config["run_id"] != EXPECTED_RUN_ID or config["opening_id"] != EXPECTED_OPENING_ID:
        raise ValueError("unexpected runtime identity")
    if config["provider_max_attempts"] != 1 or config["provider_retry_allowed"] is not False:
        raise ValueError("requests must use exactly one provider attempt")
    for field in (
        "tool_execution_allowed",
        "independent_validation_split_access_allowed",
        "confirmatory_inference_allowed",
        "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")
    paths = {name: validate_binding(binding) for name, binding in config["bindings"].items()}
    documents = {name: load_json(path) for name, path in paths.items()}
    manifest = documents["opening_manifest"]
    opening_dir = paths["opening_manifest"].parent
    manifest_rows = {row["filename"]: row for row in manifest["artifacts"]}
    if len(manifest_rows) != manifest["artifact_count"]:
        raise ValueError("opening manifest contains duplicate artifacts")
    for filename, row in manifest_rows.items():
        artifact = opening_dir / filename
        if not artifact.is_file() or file_hash(artifact) != row["sha256"]:
            raise ValueError(f"opening artifact hash mismatch: {filename}")
    preflight = documents["opening_preflight"]
    if preflight["opening_status"] != "prepared_local_gate_passed_pending_external_authorization":
        raise ValueError("opening preflight is not eligible")
    if not all(preflight["checks"].values()):
        raise ValueError("opening preflight checks are incomplete")
    tasks = documents["input_tasks"]["tasks"]
    views = documents["candidate_views"]["views"]
    cells = documents["run_cells"]["cells"]
    if len(tasks) != 8 or len(views) != 50 or len(cells) != config["scheduled_request_count"]:
        raise ValueError("opening dimensions changed")
    task_by_id = {row["task_id"]: row for row in tasks}
    view_by_id = {row["candidate_view_id"]: row for row in views}
    if len(task_by_id) != 8 or len(view_by_id) != 50 or len({row["cell_id"] for row in cells}) != 64:
        raise ValueError("opening identifiers are duplicated")
    for cell in cells:
        view = view_by_id[cell["candidate_view_id"]]
        if view["method"] != cell["method"] or view["tool_pool_size"] != cell["tool_pool_size"]:
            raise ValueError(f"cell/view mismatch: {cell['cell_id']}")
        names = [tool["function"]["name"] for tool in view["openai_tools"]]
        if names != view["ordered_candidate_tool_ids"]:
            raise ValueError(f"schema order mismatch: {view['candidate_view_id']}")
        if cell["tool_execution_allowed"] is not False or cell["gold_visible_to_router"] is not False:
            raise ValueError(f"unsafe cell policy: {cell['cell_id']}")
    return {
        "paths": paths,
        "documents": documents,
        "tasks": tasks,
        "views": views,
        "cells": cells,
        "task_by_id": task_by_id,
        "view_by_id": view_by_id,
        "prompt": documents["selector_prompt"],
    }


def validate_authorization(
    authorization: dict[str, Any], config: dict[str, Any], opening: dict[str, Any]
) -> None:
    expected = {
        "run_id": EXPECTED_RUN_ID,
        "opening_id": EXPECTED_OPENING_ID,
        "decision": EXPECTED_DECISION,
        "provider": config["provider"],
        "endpoint": config["openai_base_url"],
        "model": config["model"],
        "scheduled_request_count": 64,
        "opening_manifest_sha256": file_hash(opening["paths"]["opening_manifest"]),
        "runtime_config_sha256": file_hash(CONFIG_PATH),
        "runner_sha256": file_hash(Path(__file__)),
    }
    for field, value in expected.items():
        if authorization.get(field) != value:
            raise ValueError(f"execution authorization mismatch for {field}")
    policies = {
        "external_data_sharing_authorized": True,
        "external_api_execution_authorized": True,
        "tool_execution_authorized": False,
        "provider_retry_authorized": False,
        "independent_validation_split_access_authorized": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    for field, value in policies.items():
        if authorization.get(field) is not value:
            raise ValueError(f"execution authorization policy mismatch for {field}")
    for field in ("authorized_by", "authorized_at", "authorization_basis"):
        if not isinstance(authorization.get(field), str) or not authorization[field].strip():
            raise ValueError(f"execution authorization missing {field}")
    parsed = datetime.fromisoformat(authorization["authorized_at"])
    if parsed.tzinfo is None:
        raise ValueError("authorized_at must include a timezone")


def response_message(response: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(response, dict) or not isinstance(response.get("choices"), list) or not response["choices"]:
        return None
    message = response["choices"][0].get("message")
    return message if isinstance(message, dict) else None


def parse_response(response: dict[str, Any] | None) -> dict[str, Any]:
    message = response_message(response)
    if message is None:
        return {"response_shape_valid": False, "tool_call_count": 0, "exactly_one_tool_call": False, "selected_tool_id": None, "arguments_json_valid": False, "arguments": None, "plain_text_content": None}
    calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
    selected = None
    arguments = None
    arguments_valid = False
    if len(calls) == 1 and isinstance(calls[0], dict):
        function = calls[0].get("function", {})
        selected = function.get("name")
        raw = function.get("arguments")
        if isinstance(raw, str):
            try:
                arguments = json.loads(raw)
                arguments_valid = isinstance(arguments, dict)
            except json.JSONDecodeError:
                arguments = None
    return {
        "response_shape_valid": True,
        "tool_call_count": len(calls),
        "exactly_one_tool_call": len(calls) == 1,
        "selected_tool_id": selected,
        "arguments_json_valid": arguments_valid,
        "arguments": arguments,
        "plain_text_content": message.get("content"),
    }


def execute(
    config: dict[str, Any],
    opening: dict[str, Any],
    authorization: dict[str, Any],
    adapter: DeepSeekOpenAIAdapter,
    checkpoint_path: Path,
) -> dict[str, Any]:
    adapter.ensure_ready()
    if adapter.base_url != config["openai_base_url"] or adapter.model != config["model"] or adapter.thinking != config["thinking"]:
        raise ValueError("adapter endpoint, model, or thinking differs from frozen runtime")
    adapter.timeout = float(config["timeout_seconds"])
    results: list[dict[str, Any]] = []
    if checkpoint_path.is_file():
        checkpoint = load_json(checkpoint_path)
        if checkpoint.get("run_id") != EXPECTED_RUN_ID:
            raise ValueError("checkpoint belongs to another run")
        results = checkpoint.get("results", [])
    completed = {row["cell_id"] for row in results}
    if len(completed) != len(results):
        raise ValueError("checkpoint contains duplicate cells")
    for cell in opening["cells"]:
        if cell["cell_id"] in completed:
            continue
        payload = payload_for(cell, opening["task_by_id"], opening["view_by_id"], opening["prompt"], config)
        started_at = datetime.now().astimezone().isoformat()
        started = time.perf_counter()
        response = None
        provider_error = None
        try:
            response = adapter.transport(
                f"{adapter.base_url}/chat/completions",
                {"Content-Type": "application/json; charset=utf-8", "Authorization": f"Bearer {adapter.api_key}"},
                payload,
                adapter.timeout,
            )
        except LLMAdapterError as exc:
            provider_error = str(exc)
        latency_ms = (time.perf_counter() - started) * 1000.0
        parsed = parse_response(response)
        result = {
            "cell_id": cell["cell_id"],
            "task_id": cell["task_id"],
            "pool_id": cell["pool_id"],
            "pool_design": cell["pool_design"],
            "tool_pool_size": cell["tool_pool_size"],
            "method": cell["method"],
            "candidate_view_id": cell["candidate_view_id"],
            "selected_schema_tool_ids": opening["view_by_id"][cell["candidate_view_id"]]["ordered_candidate_tool_ids"],
            "request_body_sha256": json_hash(payload),
            "started_at": started_at,
            "api_latency_ms": round(latency_ms, 6),
            "transport_accepted": response_message(response) is not None,
            "provider_error": provider_error,
            "response_id": response.get("id") if isinstance(response, dict) else None,
            "response_model": response.get("model") if isinstance(response, dict) else None,
            "finish_reason": response.get("choices", [{}])[0].get("finish_reason") if isinstance(response, dict) and response.get("choices") else None,
            "usage": response.get("usage") if isinstance(response, dict) else None,
            **parsed,
            "raw_response": response,
            "tool_executed": False,
            "retry_count": 0,
            "confirmatory_inference_allowed": False,
        }
        results.append(result)
        completed.add(cell["cell_id"])
        write_json_atomic(
            checkpoint_path,
            {"schema_version": "1.0", "run_id": EXPECTED_RUN_ID, "authorization_content_sha256": json_hash(authorization), "completed_count": len(results), "results": results},
        )
        print(json.dumps({"progress": f"{len(results)}/64", "cell_id": cell["cell_id"], "accepted": result["transport_accepted"], "selected_tool_id": result["selected_tool_id"], "provider_error": provider_error}, ensure_ascii=False), flush=True)
    if len(results) != 64:
        raise ValueError("execution ended without all 64 terminal results")
    return {"schema_version": "1.0", "run_id": EXPECTED_RUN_ID, "opening_id": EXPECTED_OPENING_ID, "authorization_decision": authorization["decision"], "result_count": len(results), "results": results}


def build_outputs(
    authorization_path: Path,
    output_dir: Path,
    adapter: DeepSeekOpenAIAdapter,
) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    opening = validate_opening(config)
    authorization = load_json(authorization_path)
    validate_authorization(authorization, config, opening)
    if output_dir.exists() and (output_dir / "artifact_manifest.json").exists():
        raise FileExistsError("completed multi-target run output already exists")
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = output_dir / "multitarget_request_results.checkpoint.json"
    result_payload = execute(config, opening, authorization, adapter, checkpoint)
    results = result_payload["results"]
    write_json(output_dir / "multitarget_request_results.json", result_payload)
    accepted = sum(row["transport_accepted"] for row in results)
    function_calls = sum(row["exactly_one_tool_call"] for row in results)
    report = {
        "schema_version": "1.0",
        "run_id": EXPECTED_RUN_ID,
        "opening_id": EXPECTED_OPENING_ID,
        "run_status": "development_run_complete_pending_offline_scoring" if accepted == 64 else "development_run_complete_with_transport_failures",
        "provider": config["provider"],
        "model": config["model"],
        "scheduled_request_count": 64,
        "external_api_calls": 64,
        "transport_accepted_count": accepted,
        "exactly_one_tool_call_count": function_calls,
        "plain_text_or_non_single_call_count": 64 - function_calls,
        "provider_error_count": sum(row["provider_error"] is not None for row in results),
        "tool_calls_executed": 0,
        "retries_executed": 0,
        "independent_validation_split_accessed": False,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
    }
    write_json(output_dir / "multitarget_runtime_report.json", report)
    snapshots = {
        "multitarget_runtime_config_snapshot.json": CONFIG_PATH,
        "execution_authorization_snapshot.json": authorization_path,
        "runner_source_snapshot.py": Path(__file__),
    }
    for filename, source in snapshots.items():
        shutil.copyfile(source, output_dir / filename)
    checkpoint.unlink(missing_ok=True)
    artifact_paths = [path for path in output_dir.iterdir() if path.is_file() and path.name != "artifact_manifest.json"]
    write_json(
        output_dir / "artifact_manifest.json",
        {"schema_version": "1.0", "run_id": EXPECTED_RUN_ID, "artifact_count": len(artifact_paths), "artifacts": [{"filename": path.name, "sha256": file_hash(path), "bytes": path.stat().st_size} for path in sorted(artifact_paths, key=lambda item: item.name)]},
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-authorization", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = build_outputs(
        args.execution_authorization.resolve(),
        args.output_dir.resolve(),
        DeepSeekOpenAIAdapter.from_environment(),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
