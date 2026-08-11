"""Execute the explicitly authorized A002/A003 Full Schema R1 once per cell."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
TOOLS_DIR = WORKSPACE / "Tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from models_core.llm_adapters import DeepSeekOpenAIAdapter, LLMAdapterError  # noqa: E402
from Tools.core_freeze.e3_routing import a004_contract_adjudication as common  # noqa: E402
from Tools.core_freeze.e3_routing.build_a002_a003_full_schema_r1_opening import canonical_hash  # noqa: E402


EXPECTED_OPENING_ID = "V11-CF05-E3-A002-A003-FULL-SCHEMA-R1-OPENING-V1-20260811"
EXPECTED_DECISION = "authorized_to_execute_a002_a003_full_schema_r1"
EXPECTED_COUNT = 64


def write_json_atomic(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    common.write_json(temporary, value)
    temporary.replace(path)


def validate_opening(opening_dir: Path) -> dict[str, Any]:
    names = {
        "config": "a002_a003_full_schema_r1_config_snapshot.json",
        "prompt": "a002_a003_full_schema_r1_prompt_snapshot.json",
        "cells": "a002_a003_full_schema_r1_run_cells.json",
        "requests": "a002_a003_full_schema_r1_request_payloads.json",
        "report": "a002_a003_full_schema_r1_opening_report.json",
        "authorization_request": "execution_authorization_request.json",
        "manifest": "artifact_manifest.json",
    }
    paths = {key: opening_dir / name for key, name in names.items()}
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    manifest = common.load_json(paths["manifest"])
    if manifest["opening_id"] != EXPECTED_OPENING_ID or manifest["artifact_count"] != 6:
        raise ValueError("opening manifest identity or count changed")
    for row in manifest["artifacts"]:
        path = opening_dir / row["filename"]
        if not path.is_file() or common.file_hash(path) != row["sha256"]:
            raise ValueError(f"opening artifact hash mismatch: {row['filename']}")
    config = common.load_json(paths["config"])
    report = common.load_json(paths["report"])
    if config["opening_id"] != EXPECTED_OPENING_ID or config["external_api_calls_authorized"] is not False:
        raise ValueError("opening config must remain pre-authorization")
    if config["automatic_retry_allowed"] is not False or config["tool_execution_allowed"] is not False:
        raise ValueError("opening retry/tool policy changed")
    if report["status"] != "execution_ready_but_external_api_unauthorized":
        raise ValueError("opening is not execution ready")
    cells = common.load_json(paths["cells"])["cells"]
    requests = common.load_json(paths["requests"])["requests"]
    request_by_id = {row["cell_id"]: row["payload"] for row in requests}
    if len(cells) != EXPECTED_COUNT or len(request_by_id) != EXPECTED_COUNT:
        raise ValueError("opening cell/request count changed")
    for cell in cells:
        payload = request_by_id.get(cell["cell_id"])
        if payload is None or canonical_hash(payload) != cell["payload_sha256"]:
            raise ValueError(f"payload hash mismatch: {cell['cell_id']}")
    return {"paths": paths, "config": config, "cells": cells, "request_by_id": request_by_id}


def validate_authorization(authorization: dict[str, Any], opening: dict[str, Any]) -> None:
    expected = {
        "opening_id": EXPECTED_OPENING_ID,
        "decision": EXPECTED_DECISION,
        "provider": "deepseek",
        "model": opening["config"]["model"],
        "scheduled_request_count": EXPECTED_COUNT,
        "opening_manifest_sha256": common.file_hash(opening["paths"]["manifest"]),
        "runner_sha256": common.file_hash(Path(__file__)),
    }
    for field, value in expected.items():
        if authorization.get(field) != value:
            raise ValueError(f"authorization mismatch: {field}")
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
            raise ValueError(f"authorization policy mismatch: {field}")
    signed_at = datetime.fromisoformat(authorization["authorized_at"])
    if signed_at.tzinfo is None:
        raise ValueError("authorized_at must include timezone")


def parse_response(response: dict[str, Any] | None) -> dict[str, Any]:
    choices = response.get("choices") if isinstance(response, dict) else None
    message = choices[0].get("message") if isinstance(choices, list) and choices else None
    if not isinstance(message, dict):
        return {"response_shape_valid": False, "tool_call_count": 0, "exactly_one_tool_call": False, "selected_tool_id": None, "arguments_json_valid": False, "arguments": None, "plain_text_content": None}
    calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
    selected = None
    arguments = None
    valid = False
    if len(calls) == 1 and isinstance(calls[0], dict):
        function = calls[0].get("function", {})
        selected = function.get("name")
        raw = function.get("arguments")
        if isinstance(raw, str):
            try:
                arguments = json.loads(raw)
                valid = isinstance(arguments, dict)
            except json.JSONDecodeError:
                pass
    return {"response_shape_valid": True, "tool_call_count": len(calls), "exactly_one_tool_call": len(calls) == 1, "selected_tool_id": selected, "arguments_json_valid": valid, "arguments": arguments, "plain_text_content": message.get("content")}


def execute(opening: dict[str, Any], authorization: dict[str, Any], adapter: DeepSeekOpenAIAdapter, checkpoint_path: Path) -> list[dict[str, Any]]:
    adapter.ensure_ready()
    if adapter.model != opening["config"]["model"] or adapter.thinking != opening["config"]["thinking"]:
        raise ValueError("runtime model/thinking differs from opening")
    results: list[dict[str, Any]] = []
    if checkpoint_path.is_file():
        checkpoint = common.load_json(checkpoint_path)
        if checkpoint.get("opening_id") != EXPECTED_OPENING_ID:
            raise ValueError("checkpoint belongs to another opening")
        results = checkpoint.get("results", [])
    completed = {row["cell_id"] for row in results}
    if len(completed) != len(results):
        raise ValueError("checkpoint contains duplicate cells")
    for cell in opening["cells"]:
        if cell["cell_id"] in completed:
            continue
        payload = opening["request_by_id"][cell["cell_id"]]
        started_at = datetime.now(timezone.utc).isoformat()
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
        parsed = parse_response(response)
        choices = response.get("choices") if isinstance(response, dict) else None
        result = {
            **{key: cell[key] for key in ("cell_id", "task_id", "pair_id", "pair_variant", "view_id", "source_pool_id", "tool_pool_size", "pool_repeat", "method", "model_run_repeat", "payload_sha256")},
            "started_at": started_at,
            "api_latency_ms": round((time.perf_counter() - started) * 1000.0, 6),
            "transport_accepted": isinstance(choices, list) and bool(choices),
            "provider_error": provider_error,
            "response_id": response.get("id") if isinstance(response, dict) else None,
            "response_model": response.get("model") if isinstance(response, dict) else None,
            "finish_reason": choices[0].get("finish_reason") if isinstance(choices, list) and choices else None,
            "usage": response.get("usage") if isinstance(response, dict) else None,
            **parsed,
            "raw_response": response,
            "tool_executed": False,
            "retry_count": 0,
            "confirmatory_inference_allowed": False,
        }
        results.append(result)
        completed.add(cell["cell_id"])
        write_json_atomic(checkpoint_path, {"schema_version": "1.0", "opening_id": EXPECTED_OPENING_ID, "authorization_content_sha256": canonical_hash(authorization), "completed_count": len(results), "results": results})
        print(json.dumps({"progress": f"{len(results)}/{EXPECTED_COUNT}", "cell_id": cell["cell_id"], "accepted": result["transport_accepted"], "selected_tool_id": result["selected_tool_id"], "provider_error": provider_error}, ensure_ascii=False), flush=True)
    if len(results) != EXPECTED_COUNT:
        raise ValueError("execution did not create 64 terminal results")
    return results


def build_outputs(opening_dir: Path, authorization_path: Path, output_dir: Path, adapter: DeepSeekOpenAIAdapter) -> dict[str, Any]:
    opening = validate_opening(opening_dir)
    authorization = common.load_json(authorization_path)
    validate_authorization(authorization, opening)
    if output_dir.exists() and (output_dir / "artifact_manifest.json").exists():
        raise FileExistsError("completed run output already exists")
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "a002_a003_full_schema_r1_results.checkpoint.json"
    results = execute(opening, authorization, adapter, checkpoint_path)
    common.write_json(output_dir / "a002_a003_full_schema_r1_results.json", {"schema_version": "1.0", "opening_id": EXPECTED_OPENING_ID, "result_count": len(results), "results": results})
    accepted = sum(row["transport_accepted"] for row in results)
    single = sum(row["exactly_one_tool_call"] for row in results)
    report = {"schema_version": "1.0", "opening_id": EXPECTED_OPENING_ID, "run_status": "development_run_complete_pending_offline_scoring" if accepted == EXPECTED_COUNT else "development_run_complete_with_transport_failures", "provider": "deepseek", "model": opening["config"]["model"], "scheduled_request_count": EXPECTED_COUNT, "external_api_calls": EXPECTED_COUNT, "transport_accepted_count": accepted, "exactly_one_tool_call_count": single, "plain_text_or_non_single_call_count": EXPECTED_COUNT - single, "provider_error_count": sum(row["provider_error"] is not None for row in results), "tool_calls_executed": 0, "retries_executed": 0, "independent_validation_split_accessed": False, "confirmatory_inference_allowed": False, "cf05_status": "in_progress", "core_frozen": False}
    common.write_json(output_dir / "a002_a003_full_schema_r1_runtime_report.json", report)
    snapshots = {"opening_manifest_snapshot.json": opening["paths"]["manifest"], "opening_config_snapshot.json": opening["paths"]["config"], "opening_prompt_snapshot.json": opening["paths"]["prompt"], "opening_run_cells_snapshot.json": opening["paths"]["cells"], "execution_authorization_snapshot.json": authorization_path, "runner_source_snapshot.py": Path(__file__)}
    for name, source in snapshots.items():
        shutil.copyfile(source, output_dir / name)
    checkpoint_path.unlink(missing_ok=True)
    paths = sorted((path for path in output_dir.iterdir() if path.is_file()), key=lambda path: path.name)
    common.write_json(output_dir / "artifact_manifest.json", {"schema_version": "1.0", "opening_id": EXPECTED_OPENING_ID, "artifact_count": len(paths), "artifacts": [{"filename": path.name, "sha256": common.file_hash(path), "bytes": path.stat().st_size} for path in paths]})
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opening-dir", type=Path, required=True)
    parser.add_argument("--execution-authorization", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_outputs(args.opening_dir.resolve(), args.execution_authorization.resolve(), args.output_dir.resolve(), DeepSeekOpenAIAdapter.from_environment()), ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
