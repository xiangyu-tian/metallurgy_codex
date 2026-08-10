"""Execute explicitly authorized A004 hard-case R2 and R3 repeats."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing import run_e3_a004_hardcase_development as common


CONFIG_PATH = Path(__file__).with_name("a004_hardcase_repeats_runtime_config_v1.json")
EXPECTED_RUN_ID = "V11-CF05-E3-A004-HARDCASE-R2R3-20260810"
EXPECTED_OPENING_ID = "V11-CF05-E3-A004-HARDCASE-R2R3-OPENING-V1-20260810"
EXPECTED_DECISION = "authorized_to_execute_a004_hardcase_r2r3_repeats"
EXPECTED_REPEAT_IDS = [2, 3]


load_json = common.load_json
write_json = common.write_json
write_json_atomic = common.write_json_atomic
json_hash = common.json_hash
file_hash = common.file_hash
response_message = common.response_message
parse_response = common.parse_response
payload_for = common.payload_for
WORKSPACE = common.WORKSPACE


def validate_binding(binding: dict[str, str]) -> Path:
    path = WORKSPACE / binding["path"]
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = file_hash(path)
    if actual != binding["sha256"].lower():
        raise ValueError(f"bound file hash mismatch for {path}: {actual}")
    return path


def validate_opening(config: dict[str, Any]) -> dict[str, Any]:
    if config["run_id"] != EXPECTED_RUN_ID or config["opening_id"] != EXPECTED_OPENING_ID:
        raise ValueError("unexpected repeat runtime identity")
    if config["model_run_repeats"] != EXPECTED_REPEAT_IDS or config["scheduled_request_count"] != 96:
        raise ValueError("repeat grid changed")
    if config["provider_max_attempts"] != 1 or config["provider_retry_allowed"] is not False:
        raise ValueError("each cell must use one provider attempt without retries")
    for field in ("tool_execution_allowed", "independent_validation_split_access_allowed",
                  "confirmatory_inference_allowed", "core_frozen"):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")
    paths = {name: validate_binding(binding) for name, binding in config["bindings"].items()}
    docs = {name: load_json(path) for name, path in paths.items()}
    manifest = docs["opening_manifest"]
    opening_dir = paths["opening_manifest"].parent
    if manifest["artifact_count"] != 10:
        raise ValueError("repeat opening manifest count changed")
    for row in manifest["artifacts"]:
        artifact = opening_dir / row["filename"]
        if not artifact.is_file() or file_hash(artifact) != row["sha256"]:
            raise ValueError(f"repeat opening artifact hash mismatch: {row['filename']}")
    preflight = docs["opening_preflight"]
    if preflight["opening_status"] != "prepared_local_gate_passed_pending_external_authorization" or not all(preflight["checks"].values()):
        raise ValueError("repeat opening is not eligible")
    tasks = docs["input_tasks"]["tasks"]
    views = docs["candidate_views"]["views"]
    cells = docs["run_cells"]["cells"]
    if len(tasks) != 2 or len(views) != 42 or len(cells) != 96:
        raise ValueError("repeat opening dimensions changed")
    if Counter(row["model_run_repeat"] for row in cells) != Counter({2: 48, 3: 48}):
        raise ValueError("repeat allocation changed")
    if [row["model_run_repeat"] for row in cells] != [2] * 48 + [3] * 48:
        raise ValueError("R2 then R3 execution order changed")
    if len({row["cell_id"] for row in cells}) != 96:
        raise ValueError("repeat cell identifiers are duplicated")
    task_by_id = {row["task_id"]: row for row in tasks}
    view_by_id = {row["candidate_view_id"]: row for row in views}
    for cell in cells:
        view = view_by_id[cell["candidate_view_id"]]
        for field in ("method", "condition_id", "tool_pool_size"):
            if view[field] != cell[field]:
                raise ValueError(f"cell/view mismatch for {field}: {cell['cell_id']}")
        if [tool["function"]["name"] for tool in view["openai_tools"]] != view["ordered_candidate_tool_ids"]:
            raise ValueError(f"schema order mismatch: {view['candidate_view_id']}")
        if cell["tool_execution_allowed"] is not False or cell["gold_visible_to_router"] is not False:
            raise ValueError(f"unsafe repeat cell policy: {cell['cell_id']}")
    return {"paths": paths, "documents": docs, "tasks": tasks, "views": views, "cells": cells,
            "task_by_id": task_by_id, "view_by_id": view_by_id, "prompt": docs["selector_prompt"]}


def validate_authorization(authorization: dict[str, Any], config: dict[str, Any],
                           opening: dict[str, Any]) -> None:
    expected = {
        "run_id": EXPECTED_RUN_ID, "opening_id": EXPECTED_OPENING_ID,
        "decision": EXPECTED_DECISION, "provider": config["provider"],
        "endpoint": config["openai_base_url"], "model": config["model"],
        "scheduled_request_count": 96,
        "opening_manifest_sha256": file_hash(opening["paths"]["opening_manifest"]),
        "runtime_config_sha256": file_hash(CONFIG_PATH), "runner_sha256": file_hash(Path(__file__)),
    }
    for field, value in expected.items():
        if authorization.get(field) != value:
            raise ValueError(f"repeat authorization mismatch for {field}")
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
            raise ValueError(f"repeat authorization policy mismatch for {field}")
    for field in ("authorized_by", "authorized_at", "authorization_basis"):
        if not isinstance(authorization.get(field), str) or not authorization[field].strip():
            raise ValueError(f"repeat authorization missing {field}")
    if datetime.fromisoformat(authorization["authorized_at"]).tzinfo is None:
        raise ValueError("authorized_at must include timezone")


def execute(config: dict[str, Any], opening: dict[str, Any], authorization: dict[str, Any],
            adapter: common.DeepSeekOpenAIAdapter, checkpoint_path: Path) -> dict[str, Any]:
    adapter.ensure_ready()
    if adapter.base_url != config["openai_base_url"] or adapter.model != config["model"] or adapter.thinking != config["thinking"]:
        raise ValueError("adapter endpoint, model, or thinking differs from frozen repeat runtime")
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
        response, provider_error = None, None
        try:
            response = adapter.transport(
                f"{adapter.base_url}/chat/completions",
                {"Content-Type": "application/json; charset=utf-8", "Authorization": f"Bearer {adapter.api_key}"},
                payload, adapter.timeout,
            )
        except common.LLMAdapterError as exc:
            provider_error = str(exc)
        parsed = parse_response(response)
        result = {
            "cell_id": cell["cell_id"], "parent_r1_cell_id": cell["parent_r1_cell_id"],
            "planned_run_id": cell["planned_run_id"], "model_run_repeat": cell["model_run_repeat"],
            "task_id": cell["task_id"], "pool_id": cell["pool_id"], "pool_design": cell["pool_design"],
            "condition_id": cell["condition_id"], "near_neighbor_type": cell["near_neighbor_type"],
            "near_neighbor_count": cell["near_neighbor_count"], "tool_pool_size": cell["tool_pool_size"],
            "method": cell["method"], "candidate_view_id": cell["candidate_view_id"],
            "selected_schema_tool_ids": opening["view_by_id"][cell["candidate_view_id"]]["ordered_candidate_tool_ids"],
            "request_body_sha256": json_hash(payload), "started_at": started_at,
            "api_latency_ms": round((time.perf_counter() - started) * 1000.0, 6),
            "transport_accepted": response_message(response) is not None, "provider_error": provider_error,
            "response_id": response.get("id") if isinstance(response, dict) else None,
            "response_model": response.get("model") if isinstance(response, dict) else None,
            "finish_reason": response.get("choices", [{}])[0].get("finish_reason") if isinstance(response, dict) and response.get("choices") else None,
            "usage": response.get("usage") if isinstance(response, dict) else None,
            **parsed, "raw_response": response, "tool_executed": False, "retry_count": 0,
            "confirmatory_inference_allowed": False,
        }
        results.append(result)
        completed.add(cell["cell_id"])
        write_json_atomic(checkpoint_path, {"schema_version": "1.0", "run_id": EXPECTED_RUN_ID,
            "authorization_content_sha256": json_hash(authorization), "completed_count": len(results), "results": results})
        print(json.dumps({"progress": f"{len(results)}/96", "repeat": cell["model_run_repeat"],
                          "cell_id": cell["cell_id"], "accepted": result["transport_accepted"],
                          "tool_call_count": result["tool_call_count"], "selected_tool_id": result["selected_tool_id"],
                          "provider_error": provider_error}, ensure_ascii=False), flush=True)
    if len(results) != 96:
        raise ValueError("execution ended without all 96 terminal results")
    return {"schema_version": "1.0", "run_id": EXPECTED_RUN_ID, "opening_id": EXPECTED_OPENING_ID,
            "authorization_decision": authorization["decision"], "result_count": len(results), "results": results}


def build_outputs(authorization_path: Path, output_dir: Path,
                  adapter: common.DeepSeekOpenAIAdapter) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    opening = validate_opening(config)
    authorization = load_json(authorization_path)
    validate_authorization(authorization, config, opening)
    if output_dir.exists() and (output_dir / "artifact_manifest.json").exists():
        raise FileExistsError("completed R2/R3 output already exists")
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = output_dir / "a004_r2r3_request_results.checkpoint.json"
    result_payload = execute(config, opening, authorization, adapter, checkpoint)
    results = result_payload["results"]
    write_json(output_dir / "a004_r2r3_request_results.json", result_payload)
    accepted = sum(row["transport_accepted"] for row in results)
    function_calls = sum(row["exactly_one_tool_call"] for row in results)
    by_repeat = []
    for repeat in EXPECTED_REPEAT_IDS:
        subset = [row for row in results if row["model_run_repeat"] == repeat]
        by_repeat.append({"model_run_repeat": repeat, "request_count": 48,
                          "transport_accepted_count": sum(row["transport_accepted"] for row in subset),
                          "exactly_one_tool_call_count": sum(row["exactly_one_tool_call"] for row in subset),
                          "provider_error_count": sum(row["provider_error"] is not None for row in subset)})
    report = {
        "schema_version": "1.0", "run_id": EXPECTED_RUN_ID, "opening_id": EXPECTED_OPENING_ID,
        "run_status": "development_repeats_complete_pending_offline_volatility_analysis" if accepted == 96 else "development_repeats_complete_with_transport_failures",
        "provider": config["provider"], "model": config["model"], "scheduled_request_count": 96,
        "external_api_calls": 96, "transport_accepted_count": accepted,
        "exactly_one_tool_call_count": function_calls, "non_single_tool_call_count": 96 - function_calls,
        "provider_error_count": sum(row["provider_error"] is not None for row in results),
        "by_repeat": by_repeat, "tool_calls_executed": 0, "retries_executed": 0,
        "independent_validation_split_accessed": False, "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress", "core_frozen": False,
    }
    write_json(output_dir / "a004_r2r3_runtime_report.json", report)
    for filename, source in {
        "a004_repeats_runtime_config_snapshot.json": CONFIG_PATH,
        "execution_authorization_snapshot.json": authorization_path,
        "runner_source_snapshot.py": Path(__file__),
    }.items():
        shutil.copyfile(source, output_dir / filename)
    checkpoint.unlink(missing_ok=True)
    artifacts = [path for path in output_dir.iterdir() if path.is_file() and path.name != "artifact_manifest.json"]
    write_json(output_dir / "artifact_manifest.json", {"schema_version": "1.0", "run_id": EXPECTED_RUN_ID,
        "artifact_count": len(artifacts), "artifacts": [{"filename": path.name, "sha256": file_hash(path),
        "bytes": path.stat().st_size} for path in sorted(artifacts, key=lambda item: item.name)]})
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-authorization", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = build_outputs(args.execution_authorization.resolve(), args.output_dir.resolve(),
                           common.DeepSeekOpenAIAdapter.from_environment())
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
