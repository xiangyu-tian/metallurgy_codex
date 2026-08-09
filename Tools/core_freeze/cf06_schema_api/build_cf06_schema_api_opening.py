"""Build the unauthorized CF-06 17/50/100/120 Schema API launch package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "cf06_feasibility_config_v1.json"
PROMPTS_PATH = HERE / "cf06_probe_prompts_v1.json"
RUNNER_PATH = HERE / "run_cf06_schema_feasibility.py"
FUNCTION_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
EXPECTED_POOL_SIZES = [17, 50, 100, 120]
EXPECTED_PROBE_MODES = ["auto_function_call", "none_schema_visibility"]


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


def json_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate_relative_filename(filename: str) -> None:
    path = Path(filename)
    if path.is_absolute() or path.name != filename or ".." in path.parts:
        raise ValueError(f"unsafe artifact filename: {filename!r}")


def validate_catalog_manifest(config: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    binding = config["catalog_artifact_manifest"]
    manifest_path = WORKSPACE / binding["path"]
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    actual = file_hash(manifest_path)
    if actual != binding["sha256"].lower():
        raise ValueError(f"catalog manifest hash mismatch: {actual}")
    manifest = load_json(manifest_path)
    catalog_dir = WORKSPACE / config["catalog_directory"]
    rows = manifest["artifacts"]
    if len(rows) != manifest["artifact_count"]:
        raise ValueError("catalog manifest artifact count mismatch")
    if len({row["filename"] for row in rows}) != len(rows):
        raise ValueError("catalog manifest contains duplicate filenames")
    for row in rows:
        validate_relative_filename(row["filename"])
        path = catalog_dir / row["filename"]
        if not path.is_file():
            raise FileNotFoundError(path)
        if file_hash(path) != row["sha256"]:
            raise ValueError(f"catalog artifact hash mismatch: {row['filename']}")
        if path.stat().st_size != row["bytes"]:
            raise ValueError(f"catalog artifact byte count mismatch: {row['filename']}")
    return catalog_dir, manifest


def count_parameter_fields(schema: Any) -> int:
    if not isinstance(schema, dict):
        return 0
    total = len(schema.get("properties", {}))
    for child in schema.get("properties", {}).values():
        total += count_parameter_fields(child)
    items = schema.get("items")
    if isinstance(items, dict):
        total += count_parameter_fields(items)
    for branch in schema.get("anyOf", []):
        total += count_parameter_fields(branch)
    return total


def validate_tools(tools: list[dict[str, Any]], expected_count: int) -> list[str]:
    if len(tools) != expected_count:
        raise ValueError(
            f"pool {expected_count} contains {len(tools)} function definitions"
        )
    names = []
    for tool in tools:
        if tool.get("type") != "function":
            raise ValueError("only function tools are allowed")
        function = tool.get("function")
        if not isinstance(function, dict):
            raise ValueError("tool is missing its function object")
        name = function.get("name", "")
        if not FUNCTION_NAME.fullmatch(name):
            raise ValueError(f"invalid function name: {name!r}")
        if not isinstance(function.get("description"), str):
            raise ValueError(f"function description is missing: {name}")
        parameters = function.get("parameters", {})
        if parameters.get("type") != "object":
            raise ValueError(f"function parameters must be an object: {name}")
        properties = parameters.get("properties")
        required = parameters.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list):
            raise ValueError(f"invalid function properties/required: {name}")
        if not set(required).issubset(properties):
            raise ValueError(f"required parameter is absent: {name}")
        names.append(name)
    if len(names) != len(set(names)):
        raise ValueError(f"pool {expected_count} contains duplicate function names")
    return names


def messages_for(
    prompts: dict[str, Any],
    mode: str,
    formula: str,
    tool_count: int,
) -> list[dict[str, str]]:
    prompt = prompts[mode]
    return [
        {"role": "system", "content": prompt["system"]},
        {
            "role": "user",
            "content": prompt["user_template"].format(
                formula=formula,
                tool_count=tool_count,
            ),
        },
    ]


def base_payload(
    config: dict[str, Any],
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "model": config["model"],
        "messages": messages,
        "temperature": config["temperature"],
        "max_tokens": config["max_tokens"],
        "stream": False,
        "thinking": {"type": config["thinking"]},
    }


def request_record(
    *,
    request_id: str,
    request_kind: str,
    mode: str,
    tool_count: int,
    payload: dict[str, Any],
    baseline_request_id: str | None,
) -> dict[str, Any]:
    serialized = canonical_json(payload)
    return {
        "request_id": request_id,
        "request_kind": request_kind,
        "probe_mode": mode,
        "tool_count": tool_count,
        "baseline_request_id": baseline_request_id,
        "payload_sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "payload_character_count": len(serialized),
        "payload_utf8_byte_count": len(serialized.encode("utf-8")),
        "payload": payload,
    }


def build(config: dict[str, Any], prompts: dict[str, Any]) -> dict[str, Any]:
    if config["pool_sizes"] != EXPECTED_POOL_SIZES:
        raise ValueError("pool_sizes must remain the frozen 17/50/100/120 design")
    if config["probe_modes"] != EXPECTED_PROBE_MODES:
        raise ValueError("probe_modes must remain auto/none")
    if config["baseline_modes"] != EXPECTED_PROBE_MODES:
        raise ValueError("baseline_modes must match the two probe prompts")
    if config["scheduled_request_count"] != 10:
        raise ValueError("scheduled_request_count must remain 10")
    for field in (
        "tool_execution_allowed",
        "fallback_tool_count_reduction_allowed",
        "text_catalog_fallback_allowed",
        "external_api_calls_authorized",
        "confirmatory_inference_allowed",
        "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")
    if config["provider_max_attempts"] != 1:
        raise ValueError("CF-06 feasibility probes must not be silently retried")
    if prompts["prompt_id"] != "V11-CF06-FULL-SCHEMA-PROBES-V1-20260809":
        raise ValueError("unexpected CF-06 prompt version")
    authorization_path = HERE / config["execution_authorization_file"]
    if authorization_path.exists():
        raise ValueError("unexpected CF-06 execution authorization file")

    catalog_dir, catalog_manifest = validate_catalog_manifest(config)
    manifest_by_name = {
        row["filename"]: row for row in catalog_manifest["artifacts"]
    }
    tools_by_size: dict[int, list[dict[str, Any]]] = {}
    names_by_size: dict[int, list[str]] = {}
    for size in config["pool_sizes"]:
        filename = config["pool_files"][str(size)]
        validate_relative_filename(filename)
        if filename not in manifest_by_name:
            raise ValueError(f"pool file is absent from bound manifest: {filename}")
        tools = load_json(catalog_dir / filename)
        tools_by_size[size] = tools
        names_by_size[size] = validate_tools(tools, size)
        if config["target_tool_id"] not in names_by_size[size]:
            raise ValueError(f"target tool is absent from pool {size}")
    for left, right in zip(config["pool_sizes"], config["pool_sizes"][1:]):
        if names_by_size[left] != names_by_size[right][:left]:
            raise ValueError(f"tool pools are not ordered nested at {left}->{right}")

    constraints = config["provider_constraints_snapshot"]
    if max(config["pool_sizes"]) > constraints["max_function_count"]:
        raise ValueError("frozen pool exceeds the provider function-count snapshot")
    requests = []
    baseline_ids = {}
    for mode in config["baseline_modes"]:
        request_id = f"CF06-BASELINE-{mode.upper().replace('_', '-')}-V1"
        baseline_ids[mode] = request_id
        messages = messages_for(
            prompts,
            mode,
            config["target_formula"],
            0,
        )
        requests.append(
            request_record(
                request_id=request_id,
                request_kind="same_prompt_no_tools_baseline",
                mode=mode,
                tool_count=0,
                payload=base_payload(config, messages),
                baseline_request_id=None,
            )
        )

    preflight_rows = []
    for size in config["pool_sizes"]:
        tools = tools_by_size[size]
        schema_text = canonical_json(tools)
        parameter_fields = sum(
            count_parameter_fields(tool["function"]["parameters"])
            for tool in tools
        )
        mode_request_metrics = {}
        for mode in config["probe_modes"]:
            payload = base_payload(
                config,
                messages_for(
                    prompts,
                    mode,
                    config["target_formula"],
                    size,
                ),
            )
            payload["tools"] = deepcopy(tools)
            payload["tool_choice"] = (
                "auto" if mode == "auto_function_call" else "none"
            )
            request_id = f"CF06-POOL-{size}-{mode.upper().replace('_', '-')}-V1"
            row = request_record(
                request_id=request_id,
                request_kind="full_schema_api_probe",
                mode=mode,
                tool_count=size,
                payload=payload,
                baseline_request_id=baseline_ids[mode],
            )
            requests.append(row)
            mode_request_metrics[mode] = {
                "request_id": request_id,
                "payload_character_count": row["payload_character_count"],
                "payload_utf8_byte_count": row["payload_utf8_byte_count"],
            }
        preflight_rows.append(
            {
                "tool_count": size,
                "function_count_limit": constraints["max_function_count"],
                "function_count_within_documented_limit": (
                    size <= constraints["max_function_count"]
                ),
                "target_tool_present": config["target_tool_id"] in names_by_size[size],
                "unique_function_names": len(names_by_size[size]) == size,
                "schema_parameter_field_count": parameter_fields,
                "schema_character_count": len(schema_text),
                "schema_utf8_byte_count": len(schema_text.encode("utf-8")),
                "provider_exact_schema_token_count": None,
                "provider_token_measurement_status": "pending_authorized_runtime",
                "request_metrics": mode_request_metrics,
            }
        )
    if len(requests) != config["scheduled_request_count"]:
        raise ValueError("constructed request count does not match the frozen schedule")
    if len({row["request_id"] for row in requests}) != len(requests):
        raise ValueError("request IDs are not unique")

    request_bundle = {
        "schema_version": "1.0",
        "run_config_id": config["run_config_id"],
        "provider": config["provider"],
        "model": config["model"],
        "endpoint": config["openai_base_url"],
        "request_count": len(requests),
        "request_order_frozen": True,
        "requests": requests,
        "result_contract": {
            "api_acceptance_primary": "HTTP success with a parseable chat-completion response",
            "auto_function_call_diagnostic": (
                "record whether one A003 call with formula Fe2O3 is returned; a wrong "
                "selection is behavioral evidence, not automatic API rejection"
            ),
            "none_enforcement": "no tool_calls may be returned when tool_choice=none",
            "schema_visibility_diagnostic": (
                "record whether the content reports A003 and the declared tool count"
            ),
            "schema_token_measure": (
                "provider prompt_tokens minus the same-prompt no-tools baseline"
            ),
        },
    }
    preflight_checks = {
        "catalog_manifest_hash_valid": True,
        "all_catalog_artifact_hashes_valid": True,
        "exact_pool_sizes": True,
        "ordered_pool_nesting": True,
        "target_present_all_sizes": True,
        "function_names_unique_and_valid": True,
        "all_sizes_within_documented_128_function_limit": all(
            row["function_count_within_documented_limit"] for row in preflight_rows
        ),
        "request_count_is_10": len(requests) == 10,
        "no_api_key_in_bundle": "api_key" not in canonical_json(request_bundle).lower(),
        "no_fallback_or_tool_execution": (
            not config["fallback_tool_count_reduction_allowed"]
            and not config["text_catalog_fallback_allowed"]
            and not config["tool_execution_allowed"]
        ),
        "provider_token_measurement_pending": all(
            row["provider_exact_schema_token_count"] is None
            for row in preflight_rows
        ),
        "external_api_calls_zero": True,
    }
    preflight = {
        "opening_id": config["opening_id"],
        "provider_constraints_snapshot": constraints,
        "token_measurement_contract": config["token_measurement_contract"],
        "rows": preflight_rows,
        "checks": preflight_checks,
        "all_offline_preflight_checks_passed": all(preflight_checks.values()),
        "context_feasibility_status": "pending_authorized_provider_measurement",
        "external_api_calls": 0,
    }
    if not preflight["all_offline_preflight_checks_passed"]:
        failed = [name for name, value in preflight_checks.items() if not value]
        raise ValueError(f"CF-06 offline preflight failed: {failed}")
    return {
        "catalog_manifest": catalog_manifest,
        "request_bundle": request_bundle,
        "preflight": preflight,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    prompts = load_json(PROMPTS_PATH)
    built = build(config, prompts)
    output_dir.mkdir(parents=True, exist_ok=True)

    request_bundle_path = output_dir / "cf06_request_bundle.json"
    preflight_path = output_dir / "cf06_preflight_audit.json"
    config_snapshot_path = output_dir / "cf06_feasibility_config_snapshot.json"
    prompt_snapshot_path = output_dir / "cf06_probe_prompts_snapshot.json"
    catalog_manifest_snapshot_path = output_dir / "catalog_artifact_manifest_snapshot.json"
    write_json(request_bundle_path, built["request_bundle"])
    write_json(preflight_path, built["preflight"])
    write_json(config_snapshot_path, config)
    write_json(prompt_snapshot_path, prompts)
    write_json(catalog_manifest_snapshot_path, built["catalog_manifest"])

    runner_snapshot_path = output_dir / "runner_source_snapshot.py"
    builder_snapshot_path = output_dir / "opening_builder_source_snapshot.py"
    runner_snapshot_path.write_bytes(RUNNER_PATH.read_bytes())
    builder_snapshot_path.write_bytes(Path(__file__).read_bytes())

    authorization_request = {
        "schema_version": "1.0",
        "authorization_request_id": "V11-CF06-API-EXECUTION-AUTH-REQUEST-V1-20260809",
        "status": "awaiting_explicit_user_authorization",
        "requested_decision": "authorized_to_execute_cf06_feasibility",
        "authorization_channel_required": config["authorization_channel_required"],
        "run_config_id": config["run_config_id"],
        "endpoint": config["openai_base_url"],
        "model": config["model"],
        "scheduled_request_count": config["scheduled_request_count"],
        "pool_sizes": config["pool_sizes"],
        "probe_modes": config["probe_modes"],
        "request_bundle_sha256": file_hash(request_bundle_path),
        "config_sha256": file_hash(config_snapshot_path),
        "prompts_sha256": file_hash(prompt_snapshot_path),
        "runner_sha256": file_hash(runner_snapshot_path),
        "catalog_manifest_sha256": file_hash(catalog_manifest_snapshot_path),
        "authorized_payload_types": [
            "two neutral probe prompts",
            "17/50/100/120 OpenAI-format function schema arrays",
            "ten frozen chat-completion request payloads",
        ],
        "tool_execution_authorized": False,
        "fallback_tool_count_reduction_authorized": False,
        "external_data_sharing_authorized": False,
        "external_api_execution_authorized": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
        "execution_authorization_file": config["execution_authorization_file"],
        "execution_authorization_file_exists": False,
    }
    authorization_path = output_dir / "execution_authorization_request.json"
    write_json(authorization_path, authorization_request)

    report = {
        "opening_id": config["opening_id"],
        "status": "offline_preflight_passed_awaiting_explicit_api_authorization",
        "pool_sizes": config["pool_sizes"],
        "probe_modes": config["probe_modes"],
        "scheduled_request_count": config["scheduled_request_count"],
        "documented_provider_function_limit": config[
            "provider_constraints_snapshot"
        ]["max_function_count"],
        "documented_provider_context_length_tokens": config[
            "provider_constraints_snapshot"
        ]["context_length_tokens"],
        "all_offline_preflight_checks_passed": built["preflight"][
            "all_offline_preflight_checks_passed"
        ],
        "provider_token_measurement_status": "pending_authorized_runtime",
        "external_api_calls": 0,
        "external_api_execution_authorized": False,
        "tool_execution_allowed": False,
        "confirmatory_inference_allowed": False,
        "cf06_status": "in_progress",
        "core_frozen": False,
        "next_gate": "explicit user authorization bound to the opening artifact hashes",
    }
    report_path = output_dir / "cf06_opening_report.json"
    write_json(report_path, report)

    artifact_paths = [
        request_bundle_path,
        preflight_path,
        config_snapshot_path,
        prompt_snapshot_path,
        catalog_manifest_snapshot_path,
        runner_snapshot_path,
        builder_snapshot_path,
        authorization_path,
        report_path,
    ]
    manifest = {
        "opening_id": config["opening_id"],
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
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    report = build_outputs(Path(args.output_dir).resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
