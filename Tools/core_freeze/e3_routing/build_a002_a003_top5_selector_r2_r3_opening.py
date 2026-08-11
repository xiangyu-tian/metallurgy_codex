"""Build unauthorized complete R2/R3 repeats of the frozen Top-5 R1 grid."""

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

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common  # noqa: E402
from Tools.core_freeze.e3_routing.build_a002_a003_top5_selector_r1_opening import (  # noqa: E402
    canonical_hash,
)
from Tools.core_freeze.e3_routing.e3_transport_policy import (  # noqa: E402
    load_and_validate_policy,
    validate_selector_payload,
)


HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "a002_a003_top5_selector_r2_r3_opening_config_v1.json"


def validate_config(config: dict[str, Any]) -> None:
    if config["purpose"] != "complete-run variability assessment_not_failed-cell_retry":
        raise ValueError("R2/R3 purpose changed")
    if config["model_run_repeats"] != ["R2", "R3"]:
        raise ValueError("R2/R3 repeat grid changed")
    if config["source_cell_count"] != 192 or config["scheduled_cell_count"] != 384:
        raise ValueError("R2/R3 cell count changed")
    if config["thinking"] != {"type": "disabled"} or config["max_tokens"] != 256:
        raise ValueError("R2/R3 transport settings changed")
    if config["request_attempts_per_cell"] != 1:
        raise ValueError("R2/R3 must remain one attempt per new cell")
    for field in (
        "source_r1_responses_may_be_reused",
        "failed_r1_cells_only",
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
    source_cells = common.load_json(paths["r1_run_cells"])["cells"]
    source_requests = common.load_json(paths["r1_request_payloads"])["requests"]
    source_prompt = common.load_json(paths["r1_prompt"])
    r1_analysis = common.load_json(paths["r1_analysis_report"])
    policy = load_and_validate_policy()
    if len(source_cells) != 192 or len(source_requests) != 192:
        raise ValueError("R1 source grid changed")
    if r1_analysis["result_count"] != 192 or r1_analysis["retries_executed"] != 0:
        raise ValueError("R1 analysis does not support complete fresh repeats")
    if r1_analysis["status"] != "development_r1_scored_with_terminal_transport_failures":
        raise ValueError("R1 analysis status changed")
    request_by_id = {row["cell_id"]: row["payload"] for row in source_requests}
    if len(request_by_id) != 192:
        raise ValueError("R1 source requests contain duplicates")

    cells = []
    requests = []
    audit_rows = []
    sequence = 0
    for repeat in config["model_run_repeats"]:
        for source_cell in source_cells:
            sequence += 1
            source_payload = request_by_id[source_cell["cell_id"]]
            payload = deepcopy(source_payload)
            validate_selector_payload(payload)
            if canonical_hash(payload) != source_cell["payload_sha256"]:
                raise ValueError("R1 source payload hash changed")
            cell_id = source_cell["cell_id"].replace("TOP5-R1-", f"TOP5-{repeat}-", 1)
            if cell_id == source_cell["cell_id"]:
                raise ValueError("R1 cell ID does not contain the frozen repeat marker")
            cell = deepcopy(source_cell)
            cell.update(
                {
                    "sequence": sequence,
                    "cell_id": cell_id,
                    "source_r1_cell_id": source_cell["cell_id"],
                    "source_r1_sequence": source_cell["sequence"],
                    "model_run_repeat": repeat,
                    "payload_sha256": canonical_hash(payload),
                    "execution_status": "not_executed_unauthorized",
                }
            )
            cells.append(cell)
            requests.append(
                {
                    "cell_id": cell_id,
                    "source_r1_cell_id": source_cell["cell_id"],
                    "payload": payload,
                }
            )
            audit_rows.append(
                {
                    "cell_id": cell_id,
                    "source_r1_cell_id": source_cell["cell_id"],
                    "model_run_repeat": repeat,
                    "source_payload_sha256": source_cell["payload_sha256"],
                    "repeat_payload_sha256": canonical_hash(payload),
                    "payload_exactly_equal_to_r1": payload == source_payload,
                    "task_schema_prompt_and_transport_unchanged": True,
                    "new_request_required": True,
                    "source_r1_response_reuse_allowed": False,
                }
            )
    if len(cells) != 384 or len({row["cell_id"] for row in cells}) != 384:
        raise ValueError("R2/R3 grid is incomplete")
    if not all(row["payload_exactly_equal_to_r1"] for row in audit_rows):
        raise ValueError("R2/R3 changed a frozen R1 payload")
    source_repeat_counts = {
        source_id: sum(row["source_r1_cell_id"] == source_id for row in cells)
        for source_id in request_by_id
    }
    if set(source_repeat_counts.values()) != {2}:
        raise ValueError("every R1 source cell must have exactly R2 and R3")
    router_text = json.dumps({"requests": requests}, ensure_ascii=False).casefold()
    for forbidden in (
        "primary_acceptable_tools",
        "alternative_success_tools",
        "family_hit_tools",
        "scientific_success_tools",
        "api_key",
        "authorization",
    ):
        if forbidden in router_text:
            raise ValueError(f"forbidden field leaked into R2/R3 payloads: {forbidden}")
    report = {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "source_opening_id": config["source_opening_id"],
        "status": "complete_repeats_execution_ready_but_external_api_unauthorized",
        "purpose": config["purpose"],
        "source_cell_count": 192,
        "model_run_repeats": config["model_run_repeats"],
        "scheduled_cell_count": 384,
        "repeat_cell_counts": {
            repeat: sum(row["model_run_repeat"] == repeat for row in cells)
            for repeat in config["model_run_repeats"]
        },
        "method_cell_counts_per_repeat": {
            repeat: {
                method: sum(
                    row["model_run_repeat"] == repeat and row["method"] == method
                    for row in cells
                )
                for method in config["methods"]
            }
            for repeat in config["model_run_repeats"]
        },
        "payloads_exactly_equal_to_r1_count": sum(
            row["payload_exactly_equal_to_r1"] for row in audit_rows
        ),
        "failed_r1_cells_only": False,
        "source_r1_responses_reused": 0,
        "transport_policy_id": policy["policy_id"],
        "external_api_calls": 0,
        "tool_calls_executed": 0,
        "external_api_execution_authorized": False,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "next_gate": "obtain separate explicit authorization binding the exact 384-request manifest before external execution",
    }
    return {
        "cells": cells,
        "requests": requests,
        "audit_rows": audit_rows,
        "prompt": source_prompt,
        "report": report,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = common.load_json(CONFIG_PATH)
    authorization_path = HERE / config["execution_authorization_file"]
    if authorization_path.exists():
        raise ValueError("unexpected R2/R3 execution authorization file")
    result = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a002_a003_top5_selector_r2_r3_config_snapshot.json": config,
        "a002_a003_top5_selector_r2_r3_prompt_snapshot.json": result["prompt"],
        "a002_a003_top5_selector_r2_r3_run_cells.json": {
            "schema_version": "1.0",
            "cells": result["cells"],
        },
        "a002_a003_top5_selector_r2_r3_request_payloads.json": {
            "schema_version": "1.0",
            "requests": result["requests"],
        },
        "a002_a003_top5_selector_r2_r3_single_axis_audit.json": {
            "schema_version": "1.0",
            "rows": result["audit_rows"],
        },
        "a002_a003_top5_selector_r2_r3_opening_report.json": result["report"],
        "execution_authorization_request.json": {
            "schema_version": "1.0",
            "opening_id": config["opening_id"],
            "decision": "pending_user_authorization",
            "eligible_for_external_execution_authorization": True,
            "data_to_be_sent": "the same 16 frozen A002/A003 development task texts and the same 192 five-tool Schema views as R1, each once in R2 and once in R3",
            "provider": config["provider"],
            "endpoint_source": "runtime_environment_not_stored_in_artifact",
            "model": config["model"],
            "request_count": 384,
            "complete_repeat_counts": {"R2": 192, "R3": 192},
            "failed_r1_cells_only": False,
            "payloads_identical_to_r1": True,
            "thinking": config["thinking"],
            "max_tokens": config["max_tokens"],
            "request_attempts_per_cell": 1,
            "automatic_retry_allowed": False,
            "tool_execution_allowed": False,
            "independent_validation_split_access_allowed": False,
            "external_api_execution_authorized": False,
            "required_authorization": "explicit user approval binding this R2/R3 manifest before any request is sent",
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
