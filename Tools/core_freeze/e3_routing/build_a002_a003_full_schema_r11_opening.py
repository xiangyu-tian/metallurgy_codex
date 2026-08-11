"""Build the no-call R1.1 package by changing only the thinking field."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common
from Tools.core_freeze.e3_routing.build_a002_a003_full_schema_r1_opening import canonical_hash


HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "a002_a003_full_schema_r11_opening_config_v1.json"


def validate_config(config: dict[str, Any]) -> None:
    if config["correction_axis"] != "explicit_thinking_disable_only":
        raise ValueError("R1.1 correction axis changed")
    if config["thinking"] != {"type": "disabled"} or config["max_tokens"] != 256:
        raise ValueError("R1.1 must add explicit thinking disable without changing token budget")
    if config["task_count"] != 16 or config["view_count"] != 4 or config["scheduled_cell_count"] != 64:
        raise ValueError("R1.1 grid changed")
    if config["request_attempts_per_cell"] != 1 or config["source_r1_responses_may_be_reused"] is not False:
        raise ValueError("R1.1 must be a new one-attempt run")
    for field in ("automatic_retry_allowed", "tool_execution_allowed", "external_api_calls_authorized", "gold_visible_to_router", "confirmatory_inference_allowed", "independent_validation_split_access_allowed", "core_frozen"):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {name: common.validate_binding(binding) for name, binding in config["bindings"].items()}
    source_requests = common.load_json(paths["r1_request_payloads"])["requests"]
    source_cells = common.load_json(paths["r1_run_cells"])["cells"]
    analysis = common.load_json(paths["r1_analysis_report"])
    if analysis["transport_confound"]["detected"] is not True:
        raise ValueError("R1 analysis does not justify transport correction")
    if len(source_requests) != 64 or len(source_cells) != 64:
        raise ValueError("R1 source grid changed")
    request_by_id = {row["cell_id"]: row["payload"] for row in source_requests}
    cells = []
    requests = []
    audit_rows = []
    for source_cell in source_cells:
        source_payload = request_by_id[source_cell["cell_id"]]
        if "thinking" in source_payload:
            raise ValueError("R1 unexpectedly contains an explicit thinking field")
        payload = deepcopy(source_payload)
        payload["thinking"] = deepcopy(config["thinking"])
        if payload["max_tokens"] != config["max_tokens"]:
            raise ValueError("R1 token budget differs from frozen R1.1 budget")
        source_without = deepcopy(source_payload)
        corrected_without = deepcopy(payload)
        corrected_thinking = corrected_without.pop("thinking")
        if source_without != corrected_without or corrected_thinking != config["thinking"]:
            raise ValueError("R1.1 changed more than the thinking field")
        cell_id = source_cell["cell_id"].replace("-FS-R1-", "-FS-R11-", 1)
        cell = deepcopy(source_cell)
        cell.update({
            "cell_id": cell_id,
            "source_r1_cell_id": source_cell["cell_id"],
            "model_run_repeat": "R1.1",
            "payload_sha256": canonical_hash(payload),
            "execution_status": "not_executed_unauthorized",
        })
        cells.append(cell)
        requests.append({"cell_id": cell_id, "source_r1_cell_id": source_cell["cell_id"], "payload": payload})
        audit_rows.append({
            "cell_id": cell_id,
            "source_r1_cell_id": source_cell["cell_id"],
            "source_payload_sha256": source_cell["payload_sha256"],
            "r11_payload_sha256": cell["payload_sha256"],
            "changed_top_level_keys": ["thinking"],
            "source_max_tokens": source_payload["max_tokens"],
            "r11_max_tokens": payload["max_tokens"],
            "thinking": payload["thinking"],
            "single_axis_check_passed": True,
        })
    if len(cells) != 64 or len({row["cell_id"] for row in cells}) != 64:
        raise ValueError("invalid R1.1 cell grid")
    report = {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "source_opening_id": config["source_opening_id"],
        "status": "transport_corrected_execution_ready_but_unauthorized",
        "task_count": 16,
        "view_count": 4,
        "scheduled_cell_count": 64,
        "correction_axis": config["correction_axis"],
        "single_axis_audit_passed_count": sum(row["single_axis_check_passed"] for row in audit_rows),
        "explicit_thinking_disabled_count": sum(row["thinking"] == {"type": "disabled"} for row in audit_rows),
        "max_tokens_unchanged_count": sum(row["source_max_tokens"] == row["r11_max_tokens"] for row in audit_rows),
        "request_payloads_materialized": True,
        "source_r1_responses_reused": False,
        "external_api_calls": 0,
        "tool_execution_allowed": False,
        "external_api_execution_authorized": False,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "next_gate": "obtain separate explicit authorization for the exact 64 R1.1 requests; execute each once without retry or tool execution",
    }
    return {"cells": cells, "requests": requests, "audit_rows": audit_rows, "report": report}


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = common.load_json(CONFIG_PATH)
    authorization_path = HERE / config["execution_authorization_file"]
    if authorization_path.exists():
        raise ValueError("unexpected R1.1 execution authorization file")
    result = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a002_a003_full_schema_r11_config_snapshot.json": config,
        "a002_a003_full_schema_r11_prompt_snapshot.json": common.load_json(common.validate_binding(config["bindings"]["r1_prompt"])),
        "a002_a003_full_schema_r11_run_cells.json": {"schema_version": "1.0", "cells": result["cells"]},
        "a002_a003_full_schema_r11_request_payloads.json": {"schema_version": "1.0", "requests": result["requests"]},
        "a002_a003_full_schema_r11_single_axis_audit.json": {"schema_version": "1.0", "rows": result["audit_rows"]},
        "a002_a003_full_schema_r11_opening_report.json": result["report"],
    }
    for filename, value in artifacts.items():
        common.write_json(output_dir / filename, value)
    common.write_json(output_dir / "execution_authorization_request.json", {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "decision": "pending_user_authorization",
        "eligible_for_external_execution_authorization": True,
        "data_to_be_sent": "the same 16 task texts and four 17/120 A/B Full Schema views as R1, in 64 new one-attempt requests with explicit thinking disabled",
        "provider": config["provider"],
        "endpoint_source": "runtime_environment_not_stored_in_artifact",
        "model": config["model"],
        "request_count": 64,
        "only_payload_change_from_r1": {"thinking": {"type": "disabled"}},
        "max_tokens_unchanged": 256,
        "source_r1_responses_may_be_reused": False,
        "automatic_retry_allowed": False,
        "tool_execution_allowed": False,
        "independent_validation_split_access_allowed": False,
        "external_api_execution_authorized": False,
        "required_authorization": "explicit user approval binding this R1.1 manifest before any request is sent",
    })
    paths = sorted(output_dir.iterdir(), key=lambda path: path.name)
    common.write_json(output_dir / "artifact_manifest.json", {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "artifact_count": len(paths),
        "artifacts": [{"filename": path.name, "sha256": common.file_hash(path), "bytes": path.stat().st_size} for path in paths],
    })
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
