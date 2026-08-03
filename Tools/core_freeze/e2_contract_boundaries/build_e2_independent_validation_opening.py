"""Build an unauthorized E2 independent-validation opening package."""

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
PROJECT_ROOT = HERE.parents[2]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from core_freeze.e2_contract_boundaries.run_e2_development import (
    file_hash,
    load_json,
)


CONFIG_PATH = HERE / "run_config_independent_validation_v1.json"
RUNNER_PATH = HERE / "run_e2_independent_validation.py"
REQUEST_PATH = (
    HERE / "execution_authorization_request_independent_validation_v1.json"
)
AUTHORIZATION_PATH = (
    HERE / "execution_authorization_independent_validation_v1.json"
)
VALIDATION_MANIFEST_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_independent_validation_v1_candidate_20260731"
    / "artifact_manifest.json"
)
DEVELOPMENT_RUN_MANIFEST_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_hybrid_semantic_development_v1_4_20260803"
    / "artifact_manifest.json"
)
DEVELOPMENT_ANALYSIS_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_hybrid_semantic_development_analysis_v1_4_20260803"
)
DEVELOPMENT_GATE_PATH = (
    DEVELOPMENT_ANALYSIS_DIR / "development_gate_evaluation.json"
)
DEVELOPMENT_GATE_MANIFEST_PATH = (
    DEVELOPMENT_ANALYSIS_DIR / "artifact_manifest.json"
)


def validate_opening_sources() -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    request = load_json(REQUEST_PATH)
    validation_manifest = load_json(VALIDATION_MANIFEST_PATH)
    gate = load_json(DEVELOPMENT_GATE_PATH)
    if AUTHORIZATION_PATH.exists():
        raise ValueError("unexpected independent validation authorization file")
    if request["status"] != "awaiting_explicit_user_authorization":
        raise ValueError("validation authorization request must remain pending")
    if request["external_api_execution_authorized"] is not False:
        raise ValueError("opening package cannot authorize API execution")
    if request["model_execution_count"] != 0:
        raise ValueError("opening package must have zero model executions")
    if config["execution_status"] != "prepared_not_authorized":
        raise ValueError("validation config must remain unauthorized")
    if request["run_config_sha256"] != file_hash(CONFIG_PATH):
        raise ValueError("authorization request config hash mismatch")
    if request["runner_sha256"] != file_hash(RUNNER_PATH):
        raise ValueError("authorization request runner hash mismatch")
    if request["validation_manifest_sha256"] != file_hash(
        VALIDATION_MANIFEST_PATH
    ):
        raise ValueError("validation manifest hash mismatch")
    if request["development_run_manifest_sha256"] != file_hash(
        DEVELOPMENT_RUN_MANIFEST_PATH
    ):
        raise ValueError("development run manifest hash mismatch")
    if request["development_gate_manifest_sha256"] != file_hash(
        DEVELOPMENT_GATE_MANIFEST_PATH
    ):
        raise ValueError("development gate manifest hash mismatch")
    task_artifact = next(
        row
        for row in validation_manifest["artifacts"]
        if row["filename"] == "e2_validation_tasks_v1.json"
    )
    if task_artifact["sha256"] != request["task_source_sha256"]:
        raise ValueError("held-out task binding mismatch")
    if gate["all_required_checks_passed"] is not True:
        raise ValueError("development gate did not pass all checks")
    if gate["decision"] != "advance_to_validation_preparation":
        raise ValueError("development gate decision mismatch")
    if gate["validation_dataset_may_be_opened"] is not False:
        raise ValueError("development gate cannot directly open validation")
    return {
        "config": config,
        "request": request,
        "validation_manifest": validation_manifest,
        "gate": gate,
    }


def build_package(output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    values = validate_opening_sources()
    output_dir.mkdir(parents=True)
    snapshots = {
        CONFIG_PATH: output_dir / "run_config_snapshot.json",
        RUNNER_PATH: output_dir / "runner_snapshot.py",
        REQUEST_PATH: output_dir / "authorization_request_snapshot.json",
        VALIDATION_MANIFEST_PATH: (
            output_dir / "validation_candidate_manifest_snapshot.json"
        ),
        DEVELOPMENT_RUN_MANIFEST_PATH: (
            output_dir / "development_run_manifest_snapshot.json"
        ),
        DEVELOPMENT_GATE_PATH: output_dir / "development_gate_snapshot.json",
        DEVELOPMENT_GATE_MANIFEST_PATH: (
            output_dir / "development_gate_manifest_snapshot.json"
        ),
    }
    for source, target in snapshots.items():
        shutil.copyfile(source, target)
    report = {
        "schema_version": "1.0-candidate",
        "candidate_id": "E2-INDEPENDENT-VALIDATION-OPENING-V1-20260803",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "prepared_not_authorized",
        "dataset_id": values["config"]["dataset_id"],
        "task_count": values["config"]["task_count"],
        "condition_count": values["config"]["condition_count"],
        "model_run_repeats": values["config"]["model_run_repeats"],
        "model_cell_count": values["config"]["authorized_model_cell_count"],
        "conditions": [
            row["condition_id"] for row in values["config"]["conditions"]
        ],
        "development_gate": {
            "decision": values["gate"]["decision"],
            "passed_check_count": values["gate"]["passed_check_count"],
            "required_check_count": values["gate"]["required_check_count"],
        },
        "held_out_task_content_copied_into_opening": False,
        "held_out_task_content_read_by_builder": False,
        "external_api_execution_authorized": False,
        "external_api_calls": 0,
        "gold_labels_sent": False,
        "mutation_history_sent": False,
        "tool_access": "disabled",
        "model_performance_claim_allowed": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    report_path = output_dir / "opening_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    artifacts = [*snapshots.values(), report_path]
    manifest = {
        "schema_version": "1.0-candidate",
        "candidate_id": report["candidate_id"],
        "source_bindings": {
            "run_config_sha256": file_hash(CONFIG_PATH),
            "runner_sha256": file_hash(RUNNER_PATH),
            "authorization_request_sha256": file_hash(REQUEST_PATH),
            "validation_manifest_sha256": file_hash(
                VALIDATION_MANIFEST_PATH
            ),
            "development_run_manifest_sha256": file_hash(
                DEVELOPMENT_RUN_MANIFEST_PATH
            ),
            "development_gate_manifest_sha256": file_hash(
                DEVELOPMENT_GATE_MANIFEST_PATH
            ),
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
