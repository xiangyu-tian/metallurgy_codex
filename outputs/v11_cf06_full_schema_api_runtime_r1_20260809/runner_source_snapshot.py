"""Execute the frozen CF-06 Schema API probes after explicit authorization.

This runner sends the request bundle exactly as frozen. It never executes a
returned tool call, never drops tools after a provider rejection, and never
switches to a text catalog fallback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
TOOLS_DIR = WORKSPACE / "Tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from models_core.llm_adapters import (  # noqa: E402
    DeepSeekOpenAIAdapter,
    LLMAdapterError,
)


HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "cf06_feasibility_config_v1.json"
PROMPTS_PATH = HERE / "cf06_probe_prompts_v1.json"
EXPECTED_AUTH_REQUEST_ID = "V11-CF06-API-EXECUTION-AUTH-REQUEST-V1-20260809"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def validate_request_bundle(bundle: dict[str, Any], config: dict[str, Any]) -> None:
    if bundle.get("run_config_id") != config["run_config_id"]:
        raise ValueError("request bundle run_config_id mismatch")
    if bundle.get("provider") != config["provider"]:
        raise ValueError("request bundle provider mismatch")
    if bundle.get("model") != config["model"]:
        raise ValueError("request bundle model mismatch")
    if bundle.get("endpoint") != config["openai_base_url"]:
        raise ValueError("request bundle endpoint mismatch")
    requests = bundle.get("requests")
    if not isinstance(requests, list) or len(requests) != config[
        "scheduled_request_count"
    ]:
        raise ValueError("request bundle count mismatch")
    if [row["request_kind"] for row in requests[:2]] != [
        "same_prompt_no_tools_baseline",
        "same_prompt_no_tools_baseline",
    ]:
        raise ValueError("the two token baselines must run first")
    if len({row["request_id"] for row in requests}) != len(requests):
        raise ValueError("request IDs are not unique")
    for row in requests:
        payload_text = canonical_json(row["payload"])
        actual_hash = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
        if row["payload_sha256"] != actual_hash:
            raise ValueError(f"payload hash mismatch: {row['request_id']}")
        if row["payload_character_count"] != len(payload_text):
            raise ValueError(f"payload character count mismatch: {row['request_id']}")
        if row["payload_utf8_byte_count"] != len(payload_text.encode("utf-8")):
            raise ValueError(f"payload byte count mismatch: {row['request_id']}")
        payload = row["payload"]
        tools = payload.get("tools", [])
        if len(tools) != row["tool_count"]:
            raise ValueError(f"payload tool count mismatch: {row['request_id']}")
        if row["request_kind"] == "full_schema_api_probe":
            expected_choice = (
                "auto"
                if row["probe_mode"] == "auto_function_call"
                else "none"
            )
            if payload.get("tool_choice") != expected_choice:
                raise ValueError(f"tool_choice mismatch: {row['request_id']}")
        elif "tools" in payload or "tool_choice" in payload:
            raise ValueError(f"baseline contains tools: {row['request_id']}")


def validate_authorization(
    authorization: dict[str, Any],
    bundle_path: Path,
    opening_dir: Path,
    config: dict[str, Any],
) -> None:
    required_files = {
        "request_bundle_sha256": bundle_path,
        "config_sha256": opening_dir / "cf06_feasibility_config_snapshot.json",
        "prompts_sha256": opening_dir / "cf06_probe_prompts_snapshot.json",
        "runner_sha256": opening_dir / "runner_source_snapshot.py",
        "catalog_manifest_sha256": (
            opening_dir / "catalog_artifact_manifest_snapshot.json"
        ),
    }
    expected = {
        "authorization_request_id": EXPECTED_AUTH_REQUEST_ID,
        "decision": "authorized_to_execute_cf06_feasibility",
        "run_config_id": config["run_config_id"],
        "endpoint": config["openai_base_url"],
        "model": config["model"],
        "scheduled_request_count": config["scheduled_request_count"],
    }
    for field, value in expected.items():
        if authorization.get(field) != value:
            raise ValueError(f"execution authorization mismatch for {field}")
    for field, path in required_files.items():
        if not path.is_file():
            raise FileNotFoundError(path)
        actual = file_hash(path)
        if authorization.get(field) != actual:
            raise ValueError(f"execution authorization mismatch for {field}")
    if file_hash(Path(__file__)) != authorization["runner_sha256"]:
        raise ValueError("live runner does not match the authorized runner snapshot")
    if authorization.get("external_data_sharing_authorized") is not True:
        raise ValueError("external data sharing is not authorized")
    if authorization.get("external_api_execution_authorized") is not True:
        raise ValueError("external API execution is not authorized")
    if authorization.get("tool_execution_authorized") is not False:
        raise ValueError("CF-06 authorization must forbid tool execution")
    if authorization.get("fallback_tool_count_reduction_authorized") is not False:
        raise ValueError("CF-06 authorization must forbid tool-count fallback")
    if authorization.get("confirmatory_inference_allowed") is not False:
        raise ValueError("CF-06 authorization cannot permit confirmatory inference")
    if authorization.get("core_frozen") is not False:
        raise ValueError("CF-06 authorization cannot freeze the core")
    for field in ("authorized_by", "authorized_at"):
        if not isinstance(authorization.get(field), str) or not authorization[field].strip():
            raise ValueError(f"execution authorization is missing {field}")
    try:
        parsed = datetime.fromisoformat(authorization["authorized_at"])
    except ValueError as exc:
        raise ValueError("authorized_at must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("authorized_at must include a timezone")


def response_message(response: dict[str, Any]) -> dict[str, Any] | None:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message")
    return message if isinstance(message, dict) else None


def parse_json_content(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, str):
        return None
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
            if text.lower().startswith("json"):
                text = text[4:].lstrip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def diagnostics_for(
    request: dict[str, Any],
    response: dict[str, Any] | None,
) -> dict[str, Any]:
    if response is None:
        return {
            "chat_completion_shape_valid": False,
            "tool_choice_none_enforced": None,
            "auto_function_call_returned": None,
            "target_tool_selected": None,
            "target_arguments_valid": None,
            "schema_visibility_response_parseable": None,
            "schema_visibility_response_correct": None,
        }
    message = response_message(response)
    if message is None:
        return {
            "chat_completion_shape_valid": False,
            "tool_choice_none_enforced": None,
            "auto_function_call_returned": None,
            "target_tool_selected": None,
            "target_arguments_valid": None,
            "schema_visibility_response_parseable": None,
            "schema_visibility_response_correct": None,
        }
    tools = message.get("tool_calls")
    if request["request_kind"] == "same_prompt_no_tools_baseline":
        return {
            "chat_completion_shape_valid": True,
            "tool_choice_none_enforced": None,
            "auto_function_call_returned": None,
            "target_tool_selected": None,
            "target_arguments_valid": None,
            "schema_visibility_response_parseable": None,
            "schema_visibility_response_correct": None,
        }
    if request["probe_mode"] == "auto_function_call":
        exactly_one = isinstance(tools, list) and len(tools) == 1
        function = tools[0].get("function", {}) if exactly_one else {}
        selected = function.get("name") == "A003" if exactly_one else False
        try:
            arguments = json.loads(function.get("arguments", "")) if exactly_one else None
        except json.JSONDecodeError:
            arguments = None
        valid_arguments = (
            isinstance(arguments, dict) and arguments.get("formula") == "Fe2O3"
        )
        return {
            "chat_completion_shape_valid": True,
            "tool_choice_none_enforced": None,
            "auto_function_call_returned": exactly_one,
            "target_tool_selected": selected,
            "target_arguments_valid": valid_arguments,
            "schema_visibility_response_parseable": None,
            "schema_visibility_response_correct": None,
        }
    content = parse_json_content(message.get("content"))
    correct = (
        content is not None
        and content.get("target_tool_visible") is True
        and content.get("target_tool_id") == "A003"
        and content.get("declared_tool_count") == request["tool_count"]
    )
    return {
        "chat_completion_shape_valid": True,
        "tool_choice_none_enforced": not bool(tools),
        "auto_function_call_returned": None,
        "target_tool_selected": None,
        "target_arguments_valid": None,
        "schema_visibility_response_parseable": content is not None,
        "schema_visibility_response_correct": correct,
    }


def execute(
    bundle: dict[str, Any],
    config: dict[str, Any],
    adapter: DeepSeekOpenAIAdapter,
) -> dict[str, Any]:
    if config["provider_max_attempts"] != 1:
        raise ValueError("CF-06 execution must not retry or shrink rejected requests")
    if config["tool_execution_allowed"] is not False:
        raise ValueError("CF-06 must not execute returned tool calls")
    adapter.ensure_ready()
    if adapter.base_url != config["openai_base_url"]:
        raise ValueError("adapter base URL does not match the frozen config")
    if adapter.model != config["model"]:
        raise ValueError("adapter model does not match the frozen config")
    if adapter.thinking != config["thinking"]:
        raise ValueError("adapter thinking mode does not match the frozen config")
    adapter.timeout = float(config["timeout_seconds"])

    results = []
    baseline_tokens: dict[str, int] = {}
    for request in bundle["requests"]:
        payload = request["payload"]
        serialized_start = time.perf_counter()
        wire_bytes = canonical_json(payload).encode("utf-8")
        request_build_ms = (time.perf_counter() - serialized_start) * 1000
        started_at = datetime.now(timezone.utc).isoformat()
        api_started = time.perf_counter()
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
        api_latency_ms = (time.perf_counter() - api_started) * 1000
        usage = response.get("usage") if isinstance(response, dict) else None
        prompt_tokens = (
            usage.get("prompt_tokens") if isinstance(usage, dict) else None
        )
        if request["request_kind"] == "same_prompt_no_tools_baseline" and isinstance(
            prompt_tokens, int
        ):
            baseline_tokens[request["request_id"]] = prompt_tokens
        result = {
            "request_id": request["request_id"],
            "request_kind": request["request_kind"],
            "probe_mode": request["probe_mode"],
            "tool_count": request["tool_count"],
            "baseline_request_id": request["baseline_request_id"],
            "payload_sha256": request["payload_sha256"],
            "started_at": started_at,
            "request_build_ms": round(request_build_ms, 6),
            "api_latency_ms": round(api_latency_ms, 6),
            "end_to_end_ms": round(request_build_ms + api_latency_ms, 6),
            "request_utf8_byte_count": len(wire_bytes),
            "transport_accepted": response_message(response) is not None,
            "provider_error": provider_error,
            "response_id": response.get("id") if isinstance(response, dict) else None,
            "response_model": response.get("model") if isinstance(response, dict) else None,
            "finish_reason": (
                response.get("choices", [{}])[0].get("finish_reason")
                if isinstance(response, dict) and response.get("choices")
                else None
            ),
            "usage": usage,
            "provider_prompt_tokens": prompt_tokens,
            "schema_exposure_prompt_token_delta": None,
            "diagnostics": diagnostics_for(request, response),
            "raw_response": response,
            "tool_executed": False,
            "retry_count": 0,
            "fallback_applied": False,
        }
        results.append(result)

    for result in results:
        baseline_id = result["baseline_request_id"]
        if baseline_id is None:
            continue
        prompt_tokens = result["provider_prompt_tokens"]
        baseline = baseline_tokens.get(baseline_id)
        if isinstance(prompt_tokens, int) and isinstance(baseline, int):
            result["schema_exposure_prompt_token_delta"] = prompt_tokens - baseline

    probe_results = [
        row for row in results if row["request_kind"] == "full_schema_api_probe"
    ]
    baseline_results = [
        row
        for row in results
        if row["request_kind"] == "same_prompt_no_tools_baseline"
    ]
    size_rows = []
    for size in config["pool_sizes"]:
        rows = [row for row in probe_results if row["tool_count"] == size]
        auto = next(row for row in rows if row["probe_mode"] == "auto_function_call")
        none = next(
            row for row in rows if row["probe_mode"] == "none_schema_visibility"
        )
        size_rows.append(
            {
                "tool_count": size,
                "auto_request_accepted": auto["transport_accepted"],
                "none_request_accepted": none["transport_accepted"],
                "native_function_call_returned": auto["diagnostics"][
                    "auto_function_call_returned"
                ],
                "target_tool_selected": auto["diagnostics"]["target_tool_selected"],
                "target_arguments_valid": auto["diagnostics"][
                    "target_arguments_valid"
                ],
                "tool_choice_none_enforced": none["diagnostics"][
                    "tool_choice_none_enforced"
                ],
                "schema_visibility_response_correct": none["diagnostics"][
                    "schema_visibility_response_correct"
                ],
                "auto_schema_exposure_prompt_token_delta": auto[
                    "schema_exposure_prompt_token_delta"
                ],
                "none_schema_exposure_prompt_token_delta": none[
                    "schema_exposure_prompt_token_delta"
                ],
                "auto_api_latency_ms": auto["api_latency_ms"],
                "none_api_latency_ms": none["api_latency_ms"],
            }
        )
    all_baselines = all(row["transport_accepted"] for row in baseline_results)
    all_probes = all(row["transport_accepted"] for row in probe_results)
    none_enforced = all(
        row["diagnostics"]["tool_choice_none_enforced"] is True
        for row in probe_results
        if row["probe_mode"] == "none_schema_visibility"
    )
    token_deltas_available = all(
        isinstance(row["schema_exposure_prompt_token_delta"], int)
        for row in probe_results
    )
    report = {
        "run_config_id": config["run_config_id"],
        "run_status": (
            "runtime_feasible_candidate_pending_review"
            if all_baselines and all_probes and none_enforced and token_deltas_available
            else "runtime_feasibility_not_established"
        ),
        "provider": config["provider"],
        "model": config["model"],
        "pool_sizes": config["pool_sizes"],
        "request_count": len(results),
        "external_api_calls": len(results),
        "all_baselines_accepted": all_baselines,
        "all_full_schema_probes_accepted": all_probes,
        "tool_choice_none_enforced_all_sizes": none_enforced,
        "provider_token_deltas_available_all_sizes": token_deltas_available,
        "size_results": size_rows,
        "tool_calls_executed": 0,
        "fallbacks_applied": 0,
        "confirmatory_inference_allowed": False,
        "cf06_status": "in_progress_pending_review",
        "core_frozen": False,
    }
    return {"results": results, "report": report}


def build_outputs(
    *,
    bundle_path: Path,
    authorization_path: Path,
    output_dir: Path,
    adapter: DeepSeekOpenAIAdapter,
) -> dict[str, Any]:
    opening_dir = bundle_path.resolve().parent
    config_path = opening_dir / "cf06_feasibility_config_snapshot.json"
    config = load_json(config_path)
    bundle = load_json(bundle_path)
    authorization = load_json(authorization_path)
    validate_request_bundle(bundle, config)
    validate_authorization(
        authorization,
        bundle_path.resolve(),
        opening_dir,
        config,
    )
    executed = execute(bundle, config, adapter)
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "cf06_request_results.json"
    report_path = output_dir / "cf06_runtime_report.json"
    write_json(results_path, {"results": executed["results"]})
    write_json(report_path, executed["report"])

    snapshot_sources = {
        "cf06_request_bundle_snapshot.json": bundle_path,
        "cf06_feasibility_config_snapshot.json": config_path,
        "cf06_probe_prompts_snapshot.json": (
            opening_dir / "cf06_probe_prompts_snapshot.json"
        ),
        "execution_authorization_snapshot.json": authorization_path,
        "runner_source_snapshot.py": Path(__file__),
    }
    artifact_paths = [results_path, report_path]
    for filename, source in snapshot_sources.items():
        target = output_dir / filename
        target.write_bytes(source.read_bytes())
        artifact_paths.append(target)
    manifest = {
        "run_config_id": config["run_config_id"],
        "artifact_count": len(artifact_paths),
        "artifacts": [
            {
                "filename": path.name,
                "sha256": file_hash(path),
                "bytes": path.stat().st_size,
            }
            for path in sorted(artifact_paths, key=lambda item: item.name)
        ],
    }
    write_json(output_dir / "artifact_manifest.json", manifest)
    return executed["report"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-bundle", required=True, type=Path)
    parser.add_argument("--execution-authorization", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    adapter = DeepSeekOpenAIAdapter.from_environment()
    report = build_outputs(
        bundle_path=args.request_bundle.resolve(),
        authorization_path=args.execution_authorization.resolve(),
        output_dir=args.output_dir.resolve(),
        adapter=adapter,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
