"""Build an unopened, no-API A004 post-gate probe package."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing import a004_contract_adjudication as gate


CONFIG_PATH = Path(__file__).with_name("a004_postgate_probe_opening_config_v1.json")
FORBIDDEN_ROUTER_KEYS = {
    "acceptable_tools", "acceptable_tools_development_scope", "expected_parameters",
    "expected_tool_id", "target_tool_id", "scoring_rule",
}


def validate_config(config: dict[str, Any]) -> None:
    for field in ("external_api_calls_authorized", "tool_execution_allowed",
                  "automatic_retry_allowed", "independent_validation_claim_allowed",
                  "confirmatory_inference_allowed", "core_frozen"):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")
    if config["provider_max_attempts"] != 1 or config["model_run_repeats"] != [1]:
        raise ValueError("opening must remain one-shot R1 only")
    task_ids = [row["task_id"] for row in config["tasks"]]
    if len(task_ids) != 10 or len(task_ids) != len(set(task_ids)):
        raise ValueError("opening requires exactly ten unique probes")


def contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(FORBIDDEN_ROUTER_KEYS.intersection(value)) or any(
            contains_forbidden_key(child) for child in value.values()
        )
    if isinstance(value, list):
        return any(contains_forbidden_key(child) for child in value)
    return False


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    bound = {name: gate.validate_binding(binding) for name, binding in config["bindings"].items()}
    views = gate.load_json(bound["candidate_views"])["views"]
    matched = [row for row in views if row["candidate_view_id"] == config["source_candidate_view_id"]]
    if len(matched) != 1:
        raise ValueError("source candidate view must be unique")
    source_view = matched[0]
    if source_view["ordered_candidate_tool_ids"] != config["expected_tool_ids"]:
        raise ValueError("source view tool order changed")
    tasks = {
        "schema_version": "1.0", "opening_id": config["opening_id"],
        "router_visible": True, "gold_fields_present": False,
        "task_count": len(config["tasks"]), "tasks": deepcopy(config["tasks"]),
    }
    schema_view = {
        "schema_version": "1.0", "opening_id": config["opening_id"],
        "router_visible": True, "gold_fields_present": False,
        "source_candidate_view_id": source_view["candidate_view_id"],
        "ordered_candidate_tool_ids": source_view["ordered_candidate_tool_ids"],
        "openai_tools": source_view["openai_tools"],
        "openai_tools_sha256": source_view["openai_tools_sha256"],
    }
    prompt = gate.load_json(bound["selector_prompt"])
    run_cells = {
        "schema_version": "1.0", "opening_id": config["opening_id"],
        "router_visible": True, "gold_fields_present": False,
        "cell_count": len(config["tasks"]),
        "cells": [
            {
                "cell_id": f"{task['task_id']}-FROZEN5-R1",
                "task_id": task["task_id"], "schema_view_id": "A004-POSTGATE-FROZEN5",
                "model_run_repeat": 1, "provider_max_attempts": 1,
            }
            for task in config["tasks"]
        ],
    }
    scoring = {
        "schema_version": "1.0", "opening_id": config["opening_id"],
        "router_visible": False, "offline_scoring_only": True,
        "tasks": [
            {
                "task_id": task["task_id"], "acceptable_tools_development_scope": ["A004"],
                "expected_parameters": {"compositions": gate.first_json_object(task["problem_text"])},
            }
            for task in config["tasks"]
        ],
    }
    router_artifacts = [tasks, schema_view, prompt, run_cells]
    if any(contains_forbidden_key(value) for value in router_artifacts):
        raise ValueError("gold field leaked into router-visible artifacts")
    preflight = {
        "schema_version": "1.0", "opening_id": config["opening_id"],
        "opening_status": "prepared_local_gate_passed_pending_external_authorization",
        "checks": {
            "all_bound_hashes_valid": True,
            "ten_unique_unrun_probes": True,
            "frozen_five_tool_schema_order": True,
            "single_attempt_r1_only": True,
            "gold_fields_absent_from_router_artifacts": True,
            "contract_gate_hash_bound": True,
            "external_api_calls_zero": True,
            "tool_execution_zero": True,
        },
        "external_api_calls": 0, "tool_calls_executed": 0,
        "confirmatory_inference_allowed": False, "cf05_status": "in_progress",
        "core_frozen": False,
    }
    authorization = {
        "schema_version": "1.0", "opening_id": config["opening_id"],
        "decision": "pending_user_authorization",
        "eligible_for_external_execution_authorization": True,
        "external_data_sharing_authorized": False,
        "external_api_execution_authorized": False,
        "tool_execution_allowed": False,
        "request_payloads_materialized": False,
        "required_scope_if_authorized": (
            "10 frozen A004 post-gate probes, one frozen five-tool Schema, R1 only, "
            "10 one-shot requests, no retry, no metallurgy tool execution"
        ),
    }
    return {
        "config": deepcopy(config), "tasks": tasks, "schema_view": schema_view,
        "prompt": prompt, "run_cells": run_cells, "scoring": scoring,
        "preflight": preflight, "authorization": authorization,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = gate.load_json(CONFIG_PATH)
    built = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a004_postgate_config_snapshot.json": built["config"],
        "a004_postgate_input_tasks.json": built["tasks"],
        "a004_postgate_schema_view.json": built["schema_view"],
        "a004_postgate_prompt_snapshot.json": built["prompt"],
        "a004_postgate_run_cells.json": built["run_cells"],
        "a004_postgate_scoring_registry.json": built["scoring"],
        "a004_postgate_opening_preflight.json": built["preflight"],
        "execution_authorization_request.json": built["authorization"],
    }
    for filename, value in artifacts.items():
        gate.write_json(output_dir / filename, value)
    manifest_rows = [
        {"filename": path.name, "sha256": gate.file_hash(path), "bytes": path.stat().st_size}
        for path in sorted(output_dir.iterdir(), key=lambda item: item.name)
    ]
    gate.write_json(output_dir / "artifact_manifest.json", {
        "schema_version": "1.0", "opening_id": config["opening_id"],
        "artifact_count": len(manifest_rows), "artifacts": manifest_rows,
    })
    return built["preflight"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else gate.WORKSPACE / args.output_dir
    print(json.dumps(build_outputs(output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
