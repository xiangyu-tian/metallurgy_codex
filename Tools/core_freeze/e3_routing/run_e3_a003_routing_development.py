"""Execute the authorized A003 four-method selector development run.

The runner submits the hash-frozen wire payloads once, records returned tool
calls, and never executes a returned metallurgy tool.
"""

from __future__ import annotations

import argparse
import hashlib
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


EXPECTED_OPENING_ID = "V11-CF05-E3-A003-ROUTING-EXECUTION-OPENING-V1-20260809"
EXPECTED_DECISION = "authorized_to_execute_a003_routing_development"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


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


def reconstruct_payload(
    cell: dict[str, Any],
    schema_by_id: dict[str, dict[str, Any]],
    system_prompt: str,
) -> dict[str, Any]:
    material = cell["request_body_materialization"]
    return {
        "model": material["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": material["user_problem_text"]},
        ],
        "tools": schema_by_id[cell["schema_view_id"]]["tools"],
        "tool_choice": material["tool_choice"],
        "temperature": material["temperature"],
        "max_tokens": material["max_tokens"],
        "stream": material["stream"],
        "thinking": material["thinking"],
    }


def validate_opening(opening_dir: Path) -> dict[str, Any]:
    paths = {
        "config": opening_dir / "a003_routing_execution_config_snapshot.json",
        "blueprints": opening_dir / "a003_routing_request_blueprints.json",
        "schema_views": opening_dir / "a003_routing_schema_views.json",
        "preflight": opening_dir / "a003_routing_execution_preflight.json",
        "manifest": opening_dir / "artifact_manifest.json",
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    config = load_json(paths["config"])
    blueprints = load_json(paths["blueprints"])
    schema_views = load_json(paths["schema_views"])
    preflight = load_json(paths["preflight"])
    manifest = load_json(paths["manifest"])
    if config["opening_id"] != EXPECTED_OPENING_ID:
        raise ValueError("unexpected A003 opening ID")
    if config["external_api_calls_authorized"] is not False:
        raise ValueError("opening config must remain pre-authorization")
    if config["tool_execution_allowed"] is not False:
        raise ValueError("opening config must prohibit tool execution")
    if config["provider_max_attempts"] != 1:
        raise ValueError("provider requests must not be retried")
    if preflight["opening_status"] != "prepared_eligible_pending_explicit_authorization":
        raise ValueError("opening preflight is not eligible")
    if not all(preflight["checks"].values()):
        raise ValueError("opening preflight checks are incomplete")
    cells = blueprints["cells"]
    if blueprints["cell_count"] != 96 or len(cells) != 96:
        raise ValueError("expected exactly 96 request blueprints")
    if len({row["cell_id"] for row in cells}) != 96:
        raise ValueError("request blueprint IDs are not unique")
    view_by_id = {row["schema_view_id"]: row for row in schema_views["views"]}
    if len(view_by_id) != schema_views["view_count"]:
        raise ValueError("schema view IDs are not unique")
    prompt = load_json(WORKSPACE / "Tools/core_freeze/e3_routing/a003_routing_prompt_v1.json")
    for cell in cells:
        payload = reconstruct_payload(cell, view_by_id, prompt["system"])
        if json_hash(payload) != cell["request_body_sha256"]:
            raise ValueError(f"request body hash mismatch: {cell['cell_id']}")
        if cell["tool_execution_allowed"] is not False:
            raise ValueError(f"cell permits tool execution: {cell['cell_id']}")
    actual_files = {
        row["filename"]: row for row in manifest["artifacts"]
    }
    if len(actual_files) != manifest["artifact_count"]:
        raise ValueError("opening manifest contains duplicate artifacts")
    for filename, row in actual_files.items():
        path = opening_dir / filename
        if not path.is_file() or file_hash(path) != row["sha256"]:
            raise ValueError(f"opening artifact hash mismatch: {filename}")
    return {
        "paths": paths,
        "config": config,
        "blueprints": blueprints,
        "schema_views": schema_views,
        "schema_by_id": view_by_id,
        "system_prompt": prompt["system"],
    }


def validate_authorization(
    authorization: dict[str, Any], opening: dict[str, Any], authorization_path: Path
) -> None:
    config = opening["config"]
    expected = {
        "opening_id": EXPECTED_OPENING_ID,
        "decision": EXPECTED_DECISION,
        "provider": config["provider"],
        "endpoint": config["openai_base_url"],
        "model": config["model"],
        "scheduled_request_count": 96,
        "opening_manifest_sha256": file_hash(opening["paths"]["manifest"]),
        "config_sha256": file_hash(opening["paths"]["config"]),
        "blueprints_sha256": file_hash(opening["paths"]["blueprints"]),
        "schema_views_sha256": file_hash(opening["paths"]["schema_views"]),
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
    for field, expected_value in policies.items():
        if authorization.get(field) is not expected_value:
            raise ValueError(f"execution authorization policy mismatch for {field}")
    for field in ("authorized_by", "authorized_at", "authorization_basis"):
        if not isinstance(authorization.get(field), str) or not authorization[field].strip():
            raise ValueError(f"execution authorization missing {field}")
    parsed = datetime.fromisoformat(authorization["authorized_at"])
    if parsed.tzinfo is None:
        raise ValueError("authorized_at must include a timezone")


def response_message(response: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(response, dict):
        return None
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message")
    return message if isinstance(message, dict) else None


def parse_response(response: dict[str, Any] | None) -> dict[str, Any]:
    message = response_message(response)
    if message is None:
        return {
            "response_shape_valid": False,
            "tool_call_count": 0,
            "exactly_one_tool_call": False,
            "selected_tool_id": None,
            "arguments_json_valid": False,
            "arguments": None,
            "plain_text_content": None,
        }
    tool_calls = message.get("tool_calls")
    calls = tool_calls if isinstance(tool_calls, list) else []
    selected_tool_id = None
    arguments = None
    arguments_valid = False
    if len(calls) == 1 and isinstance(calls[0], dict):
        function = calls[0].get("function", {})
        selected_tool_id = function.get("name")
        raw_arguments = function.get("arguments")
        if isinstance(raw_arguments, str):
            try:
                arguments = json.loads(raw_arguments)
                arguments_valid = isinstance(arguments, dict)
            except json.JSONDecodeError:
                arguments = None
    return {
        "response_shape_valid": True,
        "tool_call_count": len(calls),
        "exactly_one_tool_call": len(calls) == 1,
        "selected_tool_id": selected_tool_id,
        "arguments_json_valid": arguments_valid,
        "arguments": arguments,
        "plain_text_content": message.get("content"),
    }


def execute(
    opening: dict[str, Any],
    authorization: dict[str, Any],
    adapter: DeepSeekOpenAIAdapter,
    checkpoint_path: Path,
) -> dict[str, Any]:
    config = opening["config"]
    adapter.ensure_ready()
    if adapter.base_url != config["openai_base_url"]:
        raise ValueError("adapter endpoint differs from frozen config")
    if adapter.model != config["model"] or adapter.thinking != config["thinking"]:
        raise ValueError("adapter model or thinking mode differs from frozen config")
    adapter.timeout = float(config["timeout_seconds"])
    results: list[dict[str, Any]] = []
    if checkpoint_path.is_file():
        checkpoint = load_json(checkpoint_path)
        if checkpoint.get("opening_id") != EXPECTED_OPENING_ID:
            raise ValueError("checkpoint belongs to another opening")
        results = checkpoint.get("results", [])
    completed = {row["cell_id"] for row in results}
    if len(completed) != len(results):
        raise ValueError("checkpoint contains duplicate cells")
    cells = opening["blueprints"]["cells"]
    for index, cell in enumerate(cells, start=1):
        if cell["cell_id"] in completed:
            continue
        payload = reconstruct_payload(
            cell, opening["schema_by_id"], opening["system_prompt"]
        )
        started_at = datetime.now(timezone.utc).isoformat()
        started = time.perf_counter()
        response = None
        provider_error = None
        try:
            response = adapter.transport(
                f"{adapter.base_url}/chat/completions",
                {
                    "Content-Type": "application/json; charset=utf-8",
                    "Authorization": f"Bearer {adapter.api_key}",
                },
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
            "tool_pool_size": cell["tool_pool_size"],
            "pool_repeat": cell["pool_repeat"],
            "near_neighbor_type": cell["near_neighbor_type"],
            "near_neighbor_count": cell["near_neighbor_count"],
            "method": cell["method"],
            "selected_schema_tool_ids": cell["selected_tool_ids"],
            "request_body_sha256": cell["request_body_sha256"],
            "started_at": started_at,
            "api_latency_ms": round(latency_ms, 6),
            "transport_accepted": response_message(response) is not None,
            "provider_error": provider_error,
            "response_id": response.get("id") if isinstance(response, dict) else None,
            "response_model": response.get("model") if isinstance(response, dict) else None,
            "finish_reason": (
                response.get("choices", [{}])[0].get("finish_reason")
                if isinstance(response, dict) and response.get("choices")
                else None
            ),
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
            {
                "schema_version": "1.0",
                "opening_id": EXPECTED_OPENING_ID,
                "authorization_content_sha256": json_hash(authorization),
                "completed_count": len(results),
                "results": results,
            },
        )
        print(
            json.dumps(
                {
                    "progress": f"{len(results)}/96",
                    "cell_id": cell["cell_id"],
                    "accepted": result["transport_accepted"],
                    "selected_tool_id": result["selected_tool_id"],
                    "provider_error": result["provider_error"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    if len(results) != 96:
        raise ValueError("execution ended without all 96 terminal results")
    return {
        "schema_version": "1.0",
        "opening_id": EXPECTED_OPENING_ID,
        "authorization_decision": authorization["decision"],
        "result_count": len(results),
        "results": results,
    }


def build_outputs(
    opening_dir: Path,
    authorization_path: Path,
    output_dir: Path,
    adapter: DeepSeekOpenAIAdapter,
) -> dict[str, Any]:
    opening = validate_opening(opening_dir)
    authorization = load_json(authorization_path)
    validate_authorization(authorization, opening, authorization_path)
    if output_dir.exists() and (output_dir / "artifact_manifest.json").exists():
        raise FileExistsError("completed routing run output already exists")
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "a003_routing_request_results.checkpoint.json"
    result_payload = execute(opening, authorization, adapter, checkpoint_path)
    results = result_payload["results"]
    results_path = output_dir / "a003_routing_request_results.json"
    write_json(results_path, result_payload)
    accepted = sum(row["transport_accepted"] for row in results)
    function_calls = sum(row["exactly_one_tool_call"] for row in results)
    report = {
        "schema_version": "1.0",
        "opening_id": EXPECTED_OPENING_ID,
        "run_status": (
            "development_run_complete_pending_offline_scoring"
            if accepted == 96
            else "development_run_complete_with_transport_failures"
        ),
        "provider": opening["config"]["provider"],
        "model": opening["config"]["model"],
        "scheduled_request_count": 96,
        "external_api_calls": 96,
        "transport_accepted_count": accepted,
        "exactly_one_tool_call_count": function_calls,
        "plain_text_or_non_single_call_count": 96 - function_calls,
        "provider_error_count": sum(row["provider_error"] is not None for row in results),
        "tool_calls_executed": 0,
        "retries_executed": 0,
        "independent_validation_split_accessed": False,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
    }
    report_path = output_dir / "a003_routing_runtime_report.json"
    write_json(report_path, report)
    snapshots = {
        "a003_routing_execution_config_snapshot.json": opening["paths"]["config"],
        "a003_routing_request_blueprints_snapshot.json": opening["paths"]["blueprints"],
        "a003_routing_schema_views_snapshot.json": opening["paths"]["schema_views"],
        "execution_authorization_snapshot.json": authorization_path,
        "runner_source_snapshot.py": Path(__file__),
    }
    for filename, source in snapshots.items():
        shutil.copyfile(source, output_dir / filename)
    checkpoint_path.unlink(missing_ok=True)
    artifact_paths = [
        path for path in output_dir.iterdir() if path.is_file() and path.name != "artifact_manifest.json"
    ]
    write_json(
        output_dir / "artifact_manifest.json",
        {
            "schema_version": "1.0",
            "opening_id": EXPECTED_OPENING_ID,
            "artifact_count": len(artifact_paths),
            "artifacts": [
                {"filename": path.name, "sha256": file_hash(path), "bytes": path.stat().st_size}
                for path in sorted(artifact_paths, key=lambda item: item.name)
            ],
        },
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--opening-dir", required=True, type=Path)
    parser.add_argument("--execution-authorization", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    report = build_outputs(
        args.opening_dir.resolve(),
        args.execution_authorization.resolve(),
        args.output_dir.resolve(),
        DeepSeekOpenAIAdapter.from_environment(),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
