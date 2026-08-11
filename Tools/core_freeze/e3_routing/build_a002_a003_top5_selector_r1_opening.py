"""Build the unauthorized 192-cell A002/A003 Top-5 selector R1 opening."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common  # noqa: E402
from Tools.core_freeze.e3_routing.e3_transport_policy import (  # noqa: E402
    load_and_validate_policy,
    validate_selector_payload,
)


HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "a002_a003_top5_selector_r1_opening_config_v1.json"


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_config(config: dict[str, Any]) -> None:
    if config["methods"] != ["lexical_top5", "dense_top5", "hierarchical"]:
        raise ValueError("Top-5 method grid changed")
    if (
        config["task_count"] != 16
        or config["source_pool_view_count"] != 4
        or config["schema_view_count"] != 192
        or config["scheduled_cell_count"] != 192
    ):
        raise ValueError("Top-5 opening grid changed")
    if config["thinking"] != {"type": "disabled"} or config["max_tokens"] != 256:
        raise ValueError("frozen selector transport parameters changed")
    if config["request_attempts_per_cell"] != 1:
        raise ValueError("each selector cell must remain single-attempt")
    for field in (
        "automatic_retry_allowed",
        "tool_execution_allowed",
        "external_api_calls_authorized",
        "gold_visible_to_router",
        "confirmatory_inference_allowed",
        "independent_validation_split_access_allowed",
        "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {
        name: common.validate_binding(binding)
        for name, binding in config["bindings"].items()
    }
    tasks = common.load_json(paths["router_tasks"])["tasks"]
    schema_views = common.load_json(paths["schema_views"])["views"]
    retrieval_rows = common.load_json(paths["retrieval_results"])["rows"]
    report = common.load_json(paths["top5_report"])
    prompt = common.load_json(paths["selector_prompt"])
    policy = load_and_validate_policy()
    if report["status"] != "top5_views_built_development_opening_eligible":
        raise ValueError("Top-5 recall gate has not passed")
    if report["all_cells_primary_acceptable_recall_at_5"] is not True:
        raise ValueError("not every Top-5 view recalls a primary acceptable tool")
    if len(tasks) != 16 or len(schema_views) != 192 or len(retrieval_rows) != 192:
        raise ValueError("bound Top-5 grid is incomplete")
    task_by_id = {row["task_id"]: row for row in tasks}
    retrieval_by_id = {row["retrieval_id"]: row for row in retrieval_rows}
    if len(task_by_id) != 16 or len(retrieval_by_id) != 192:
        raise ValueError("duplicate task or retrieval identifiers")

    cells = []
    requests = []
    for sequence, view in enumerate(schema_views, start=1):
        retrieval = retrieval_by_id[view["schema_view_id"]]
        task = task_by_id[view["task_id"]]
        if view["method"] != retrieval["method"]:
            raise ValueError("schema view method differs from retrieval result")
        if view["ordered_tool_ids"] != retrieval["selected_tool_ids"]:
            raise ValueError("schema view tool order differs from retrieval result")
        if len(view["tools"]) != 5 or len(view["ordered_tool_ids"]) != 5:
            raise ValueError("each Top-5 request must expose exactly five tools")
        payload = {
            "model": config["model"],
            "messages": [
                {"role": "system", "content": prompt["system"]},
                {
                    "role": "user",
                    "content": prompt["user_template"].format(
                        problem_text=task["problem_text"]
                    ),
                },
            ],
            "tools": view["tools"],
            "tool_choice": prompt["selector_policy"]["tool_choice"],
            "temperature": config["temperature"],
            "max_tokens": config["max_tokens"],
            "thinking": config["thinking"],
        }
        validate_selector_payload(payload)
        cell_id = f"A002-A003-TOP5-R1-{view['schema_view_id']}"
        cells.append(
            {
                "sequence": sequence,
                "cell_id": cell_id,
                "task_id": view["task_id"],
                "pair_id": task["pair_id"],
                "pair_variant": task["pair_variant"],
                "source_pool_view_id": view["source_pool_view_id"],
                "method": view["method"],
                "schema_view_id": view["schema_view_id"],
                "visible_tool_ids": view["ordered_tool_ids"],
                "visible_tool_count": 5,
                "model_run_repeat": config["model_run_repeat"],
                "request_attempt_limit": 1,
                "payload_sha256": canonical_hash(payload),
                "execution_status": "not_executed_unauthorized",
            }
        )
        requests.append({"cell_id": cell_id, "payload": payload})

    if len(cells) != 192 or len({row["cell_id"] for row in cells}) != 192:
        raise ValueError("invalid Top-5 selector cell grid")
    method_counts = {
        method: sum(row["method"] == method for row in cells)
        for method in config["methods"]
    }
    if method_counts != {method: 64 for method in config["methods"]}:
        raise ValueError("Top-5 method cell counts changed")
    forbidden = set(prompt["gold_fields_forbidden"])
    router_text = json.dumps({"tasks": tasks, "requests": requests}, ensure_ascii=False)
    if any(f'"{field}"' in router_text for field in forbidden):
        raise ValueError("gold leaked into router-visible package")
    if "api_key" in router_text.casefold():
        raise ValueError("API key leaked into opening package")
    opening_report = {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "status": "execution_ready_but_external_api_unauthorized",
        "task_count": len(tasks),
        "schema_view_count": len(schema_views),
        "scheduled_cell_count": len(cells),
        "method_cell_counts": method_counts,
        "visible_tools_per_request": 5,
        "explicit_thinking_disabled_count": sum(
            row["payload"]["thinking"] == {"type": "disabled"}
            for row in requests
        ),
        "transport_policy_id": policy["policy_id"],
        "request_payloads_materialized": True,
        "gold_visible_to_router": False,
        "external_api_calls": 0,
        "tool_calls_executed": 0,
        "external_api_execution_authorized": False,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "next_gate": "obtain separate explicit authorization binding this exact 192-request manifest before external execution",
    }
    return {
        "cells": cells,
        "requests": requests,
        "prompt": prompt,
        "report": opening_report,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = common.load_json(CONFIG_PATH)
    authorization_path = HERE / config["execution_authorization_file"]
    if authorization_path.exists():
        raise ValueError("unexpected Top-5 execution authorization file")
    result = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a002_a003_top5_selector_r1_config_snapshot.json": config,
        "a002_a003_top5_selector_r1_prompt_snapshot.json": result["prompt"],
        "a002_a003_top5_selector_r1_run_cells.json": {
            "schema_version": "1.0",
            "cells": result["cells"],
        },
        "a002_a003_top5_selector_r1_request_payloads.json": {
            "schema_version": "1.0",
            "requests": result["requests"],
        },
        "a002_a003_top5_selector_r1_opening_report.json": result["report"],
        "execution_authorization_request.json": {
            "schema_version": "1.0",
            "opening_id": config["opening_id"],
            "decision": "pending_user_authorization",
            "eligible_for_external_execution_authorization": True,
            "data_to_be_sent": "16 frozen A002/A003 development task texts and 192 corresponding five-tool Schema views from lexical, dense-v2 and hierarchical retrieval",
            "provider": config["provider"],
            "endpoint_source": "runtime_environment_not_stored_in_artifact",
            "model": config["model"],
            "request_count": 192,
            "thinking": config["thinking"],
            "max_tokens": config["max_tokens"],
            "request_attempts_per_cell": 1,
            "automatic_retry_allowed": False,
            "tool_execution_allowed": False,
            "independent_validation_split_access_allowed": False,
            "external_api_execution_authorized": False,
            "required_authorization": "explicit user approval binding this opening manifest before any request is sent",
        },
    }
    for filename, value in artifacts.items():
        common.write_json(output_dir / filename, value)
    paths = sorted(output_dir.iterdir(), key=lambda path: path.name)
    common.write_json(
        output_dir / "artifact_manifest.json",
        {
            "schema_version": "1.0",
            "opening_id": config["opening_id"],
            "artifact_count": len(paths),
            "artifacts": [
                {
                    "filename": path.name,
                    "sha256": common.file_hash(path),
                    "bytes": path.stat().st_size,
                }
                for path in paths
            ],
        },
    )
    return result["report"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else WORKSPACE / args.output_dir
    print(json.dumps(build_outputs(output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
