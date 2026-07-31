"""Build the non-authorized opening package for E2 hybrid semantic development."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from core_freeze.e2_contract_boundaries.run_e2_development import (  # noqa: E402
    build_messages,
    file_hash,
    load_json,
)
from core_freeze.e2_contract_boundaries.run_e2_hybrid_semantic_development import (  # noqa: E402
    AUTHORIZATION_PATH,
    AUTHORIZATION_REQUEST_PATH,
    ADVANCEMENT_GATE_PATH,
    BASE_POLICY_PATH,
    CONFIG_PATH,
    CONTRACTS_PATH,
    HYBRID_POLICY_PATH,
    OUTPUT_SCHEMA_PATH,
    PROMPTS_PATH,
    TASKS_PATH,
    validate_inputs,
)


RUNNER_PATH = (
    HERE
    / "run_e2_hybrid_semantic_development.py"
)
ANALYZER_PATH = (
    HERE / "analyze_e2_hybrid_semantic_development.py"
)
FORBIDDEN_MODEL_FIELDS = (
    "task_id",
    "base_task_id",
    "base_task_group_id",
    "mutation_types",
    "mutation_ids",
    "expected_flags",
    "primary_status",
    "allowed_actions",
    "policy_expected_action",
)


def validate_opening() -> dict[str, Any]:
    values = {
        "tasks": load_json(TASKS_PATH),
        "contracts": load_json(CONTRACTS_PATH),
        "prompts": load_json(PROMPTS_PATH),
        "output_schema": load_json(OUTPUT_SCHEMA_PATH),
        "base_policy": load_json(BASE_POLICY_PATH),
        "hybrid_policy": load_json(HYBRID_POLICY_PATH),
        "config": load_json(CONFIG_PATH),
        "authorization_request": load_json(
            AUTHORIZATION_REQUEST_PATH
        ),
        "advancement_gate": load_json(ADVANCEMENT_GATE_PATH),
    }
    validate_inputs(
        values["tasks"],
        values["contracts"],
        values["prompts"],
        values["output_schema"],
        values["base_policy"],
        values["hybrid_policy"],
        values["config"],
    )
    request = values["authorization_request"]
    if request["status"] != "awaiting_explicit_user_authorization":
        raise ValueError("authorization request must remain pending")
    if request["execution_authorization_file_exists"] is not False:
        raise ValueError("request cannot claim authorization exists")
    if request["external_api_execution_authorized"] is not False:
        raise ValueError("request cannot authorize API execution")
    gate = values["advancement_gate"]
    if values["config"]["advancement_gate_id"] != gate["gate_id"]:
        raise ValueError("run config advancement gate ID mismatch")
    if request["advancement_gate_id"] != gate["gate_id"]:
        raise ValueError("authorization request gate ID mismatch")
    if request["advancement_gate_sha256"] != file_hash(
        ADVANCEMENT_GATE_PATH
    ):
        raise ValueError("authorization request gate hash mismatch")
    if AUTHORIZATION_PATH.exists():
        raise ValueError("unexpected hybrid semantic authorization file")
    if values["config"]["execution_status"] != "prepared_not_authorized":
        raise ValueError("run config must remain not authorized")
    return values


def audit_model_payloads(values: dict[str, Any]) -> dict[str, Any]:
    contracts = {
        row["tool_id"]: row for row in values["contracts"]["contracts"]
    }
    rows = []
    errors = []
    for task in values["tasks"]["tasks"]:
        messages = build_messages(
            task,
            contracts[task["source_tool_id"]],
            values["prompts"],
        )
        serialized = json.dumps(messages, ensure_ascii=False)
        visible_text = "\n".join(
            message["content"] for message in messages
        )
        leaked_fields = [
            field
            for field in FORBIDDEN_MODEL_FIELDS
            if f'"{field}"' in visible_text
        ]
        leaked_values = [
            field
            for field in (
                "task_id",
                "base_task_id",
                "base_task_group_id",
            )
            if str(task[field]) in visible_text
        ]
        if leaked_fields or leaked_values:
            errors.append(
                {
                    "task_id": task["task_id"],
                    "leaked_fields": leaked_fields,
                    "leaked_identifier_values": leaked_values,
                }
            )
        rows.append(
            {
                "task_id": task["task_id"],
                "source_tool_id": task["source_tool_id"],
                "message_sha256": _text_hash(serialized),
                "message_count": len(messages),
                "forbidden_field_count": len(leaked_fields),
                "forbidden_identifier_value_count": len(leaked_values),
            }
        )
    return {
        "schema_version": "1.3-candidate",
        "audit_id": "E2-HYBRID-SEMANTIC-DEV-V1.3-PAYLOAD-AUDIT-20260731",
        "task_count": len(rows),
        "status": "passed" if not errors else "failed",
        "forbidden_fields": list(FORBIDDEN_MODEL_FIELDS),
        "leakage_error_count": len(errors),
        "errors": errors,
        "payload_hashes": rows,
        "gold_labels_sent": False,
        "mutation_history_sent": False,
        "validation_dataset_sent": False,
        "external_api_calls": 0,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }


def _text_hash(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_package(output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    values = validate_opening()
    payload_audit = audit_model_payloads(values)
    if payload_audit["status"] != "passed":
        raise ValueError("model payload leakage audit failed")
    output_dir.mkdir(parents=True)
    snapshots = {
        TASKS_PATH: output_dir / "task_source_snapshot.json",
        CONTRACTS_PATH: output_dir / "contracts_snapshot.json",
        BASE_POLICY_PATH: output_dir / "base_policy_snapshot.json",
        HYBRID_POLICY_PATH: output_dir / "hybrid_policy_snapshot.json",
        ADVANCEMENT_GATE_PATH: (
            output_dir / "advancement_gate_snapshot.json"
        ),
        PROMPTS_PATH: output_dir / "prompt_snapshot.json",
        OUTPUT_SCHEMA_PATH: output_dir / "output_schema_snapshot.json",
        CONFIG_PATH: output_dir / "run_config_snapshot.json",
        AUTHORIZATION_REQUEST_PATH: (
            output_dir / "execution_authorization_request_snapshot.json"
        ),
        RUNNER_PATH: output_dir / "runner_snapshot.py",
        ANALYZER_PATH: output_dir / "analyzer_snapshot.py",
    }
    for source, target in snapshots.items():
        shutil.copyfile(source, target)
    payload_audit_path = output_dir / "model_payload_audit.json"
    payload_audit_path.write_text(
        json.dumps(payload_audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = {
        "schema_version": "1.3-candidate",
        "candidate_id": "E2-HYBRID-SEMANTIC-DEV-OPENING-V1.3-20260731",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "prepared_not_authorized",
        "dataset_id": values["tasks"]["dataset_id"],
        "task_count": values["tasks"]["task_count"],
        "model_output_fields": ["semantic_flags"],
        "deterministic_components": [
            "structural flag derivation",
            "ordered flag merge",
            "primary status derivation",
            "action derivation",
        ],
        "execution_gate": {
            "authorization_status": "pending",
            "authorization_file_exists": False,
            "external_api_execution_authorized": False,
            "new_provider_calls": 0,
        },
        "external_data_scope": values["authorization_request"][
            "external_data_scope"
        ],
        "excluded_external_data_scope": values[
            "authorization_request"
        ]["excluded_external_data_scope"],
        "model_payload_audit": {
            "status": payload_audit["status"],
            "task_count": payload_audit["task_count"],
            "leakage_error_count": payload_audit[
                "leakage_error_count"
            ],
            "gold_labels_sent": False,
            "mutation_history_sent": False,
            "validation_dataset_sent": False,
        },
        "development_only": True,
        "advancement_gate": {
            "gate_id": values["advancement_gate"]["gate_id"],
            "required_check_count": len(
                values["advancement_gate"]["required_checks"]
            ),
            "partial_pass_allowed": values["advancement_gate"][
                "decision_rule"
            ]["partial_pass_allowed"],
        },
        "model_performance_claim_allowed": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    report_path = output_dir / "candidate_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    artifacts = list(snapshots.values()) + [
        payload_audit_path,
        report_path,
    ]
    manifest = {
        "schema_version": "1.3-candidate",
        "candidate_id": report["candidate_id"],
        "source_bindings": {
            "tasks_sha256": file_hash(TASKS_PATH),
            "contracts_sha256": file_hash(CONTRACTS_PATH),
            "base_policy_sha256": file_hash(BASE_POLICY_PATH),
            "hybrid_policy_sha256": file_hash(HYBRID_POLICY_PATH),
            "advancement_gate_sha256": file_hash(
                ADVANCEMENT_GATE_PATH
            ),
            "prompt_sha256": file_hash(PROMPTS_PATH),
            "output_schema_sha256": file_hash(OUTPUT_SCHEMA_PATH),
            "run_config_sha256": file_hash(CONFIG_PATH),
            "authorization_request_sha256": file_hash(
                AUTHORIZATION_REQUEST_PATH
            ),
            "runner_sha256": file_hash(RUNNER_PATH),
            "analyzer_sha256": file_hash(ANALYZER_PATH),
            "builder_sha256": file_hash(Path(__file__)),
        },
        "artifacts": [
            {"filename": path.name, "sha256": file_hash(path)}
            for path in artifacts
        ],
        "execution_status": "prepared_not_authorized",
        "external_api_calls": 0,
        "external_api_execution_authorized": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    (output_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = build_package(args.output_dir.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
