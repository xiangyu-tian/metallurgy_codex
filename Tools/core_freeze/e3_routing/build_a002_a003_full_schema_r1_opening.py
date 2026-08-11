"""Build an execution-ready but unauthorized A002/A003 full-schema R1 package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common


HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "a002_a003_full_schema_r1_opening_config_v1.json"
PROMPT_PATH = HERE / "a002_a003_full_schema_selector_prompt_v1.json"


def canonical_hash(value: Any) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_design(config: dict[str, Any], prompt: dict[str, Any]) -> None:
    if config["method"] != "full_schema":
        raise ValueError("opening must remain full_schema only")
    if config["selected_pool_sizes"] != [17, 120] or config["selected_pool_repeats"] != ["A", "B"]:
        raise ValueError("17/120 A/B grid changed")
    if config["task_count"] != 16 or config["view_count"] != 4 or config["scheduled_cell_count"] != 64:
        raise ValueError("opening grid changed")
    if config["model_run_repeat"] != 1 or config["request_attempts_per_cell"] != 1:
        raise ValueError("R1 must remain one attempt per cell")
    for field in ("automatic_retry_allowed", "tool_execution_allowed", "external_api_calls_authorized", "gold_visible_to_router", "confirmatory_inference_allowed", "independent_validation_split_access_allowed", "core_frozen"):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")
    if prompt["selector_policy"]["maximum_tool_calls"] != 1 or prompt["selector_policy"]["tool_execution_allowed"] is not False:
        raise ValueError("selector prompt policy changed")


def build(config: dict[str, Any], prompt: dict[str, Any]) -> dict[str, Any]:
    validate_design(config, prompt)
    paths = {name: common.validate_binding(binding) for name, binding in config["bindings"].items()}
    tasks_doc = common.load_json(paths["router_tasks"])
    views_doc = common.load_json(paths["pool_views"])
    scoring_doc = common.load_json(paths["scoring_registry"])
    tasks = tasks_doc["tasks"]
    views = views_doc["views"]
    if len(tasks) != 16 or len(views) != 4:
        raise ValueError("bound task or view count changed")
    scoring_keys = {(row["task_id"], row["view_id"]) for row in scoring_doc["rows"]}
    expected_keys = {(task["task_id"], view["view_id"]) for task in tasks for view in views}
    if scoring_keys != expected_keys:
        raise ValueError("pool-specific scoring grid is incomplete")

    cells = []
    requests = []
    for task in tasks:
        for view in views:
            cell_id = f"A002-A003-FS-R1-{task['task_id']}-{view['view_id']}"
            payload = {
                "model": config["model"],
                "messages": [
                    {"role": "system", "content": prompt["system"]},
                    {"role": "user", "content": prompt["user_template"].format(problem_text=task["problem_text"])},
                ],
                "tools": view["openai_tools"],
                "tool_choice": prompt["selector_policy"]["tool_choice"],
                "temperature": config["temperature"],
                "max_tokens": config["max_tokens"],
            }
            cells.append({
                "cell_id": cell_id,
                "task_id": task["task_id"],
                "pair_id": task["pair_id"],
                "pair_variant": task["pair_variant"],
                "view_id": view["view_id"],
                "source_pool_id": view["source_pool_id"],
                "tool_pool_size": view["tool_pool_size"],
                "pool_repeat": view["pool_repeat"],
                "method": "full_schema",
                "model_run_repeat": 1,
                "payload_sha256": canonical_hash(payload),
                "execution_status": "not_executed_unauthorized",
            })
            requests.append({"cell_id": cell_id, "payload": payload})
    if len(cells) != 64 or len({row["cell_id"] for row in cells}) != 64:
        raise ValueError("invalid cell grid")

    forbidden = set(prompt["gold_fields_forbidden"])
    router_text = json.dumps({"tasks": tasks, "requests": requests}, ensure_ascii=False)
    if any(f'"{field}"' in router_text for field in forbidden):
        raise ValueError("gold leaked into router-visible package")
    if "api_key" in router_text.casefold():
        raise ValueError("API key leaked into opening package")
    report = {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "status": "execution_ready_but_external_api_unauthorized",
        "task_count": 16,
        "view_count": 4,
        "scheduled_cell_count": 64,
        "counts_by_pool_size": {str(size): sum(row["tool_pool_size"] == size for row in cells) for size in config["selected_pool_sizes"]},
        "counts_by_pair_variant": {variant: sum(row["pair_variant"] == variant for row in cells) for variant in ("element_stoichiometry", "molar_mass")},
        "request_payloads_materialized": True,
        "payload_hashes_unique": len({row["payload_sha256"] for row in cells}) == 64,
        "gold_fields_absent_from_router_package": True,
        "api_key_absent": True,
        "tool_execution_allowed": False,
        "external_api_calls": 0,
        "external_api_execution_authorized": False,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "next_gate": "obtain separate explicit authorization for the exact 64 frozen requests, then execute each cell once without tool execution or retry",
    }
    return {"cells": cells, "requests": requests, "report": report}


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = common.load_json(CONFIG_PATH)
    prompt = common.load_json(PROMPT_PATH)
    authorization_path = HERE / config["execution_authorization_file"]
    if authorization_path.exists():
        raise ValueError("unexpected execution authorization file; opening builder must remain no-call")
    result = build(config, prompt)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a002_a003_full_schema_r1_config_snapshot.json": config,
        "a002_a003_full_schema_r1_prompt_snapshot.json": prompt,
        "a002_a003_full_schema_r1_run_cells.json": {"schema_version": "1.0", "cells": result["cells"]},
        "a002_a003_full_schema_r1_request_payloads.json": {"schema_version": "1.0", "requests": result["requests"]},
        "a002_a003_full_schema_r1_opening_report.json": result["report"],
    }
    for filename, value in artifacts.items():
        common.write_json(output_dir / filename, value)
    common.write_json(output_dir / "execution_authorization_request.json", {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "decision": "pending_user_authorization",
        "eligible_for_external_execution_authorization": True,
        "data_to_be_sent": "16 frozen task texts and four frozen 17/120 full-schema views as 64 one-attempt requests",
        "provider": config["provider"],
        "endpoint_source": "runtime_environment_not_stored_in_artifact",
        "model": config["model"],
        "request_count": 64,
        "automatic_retry_allowed": False,
        "tool_execution_allowed": False,
        "independent_validation_split_access_allowed": False,
        "external_api_execution_authorized": False,
        "required_authorization": "explicit user approval binding this opening package manifest before any request is sent",
    })
    artifact_paths = sorted(output_dir.iterdir(), key=lambda path: path.name)
    common.write_json(output_dir / "artifact_manifest.json", {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "artifact_count": len(artifact_paths),
        "artifacts": [{"filename": path.name, "sha256": common.file_hash(path), "bytes": path.stat().st_size} for path in artifact_paths],
    })
    return result["report"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else common.WORKSPACE / args.output_dir
    print(json.dumps(build_outputs(output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
