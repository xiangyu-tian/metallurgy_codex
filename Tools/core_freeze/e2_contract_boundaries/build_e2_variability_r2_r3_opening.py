"""Build the unauthorized CF-08 E2 R2/R3 variability opening package."""

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

from core_freeze.e2_contract_boundaries import (  # noqa: E402
    run_e2_independent_validation as base,
    run_e2_variability_r2_r3 as runner,
)
from core_freeze.e2_contract_boundaries.run_e2_development import (  # noqa: E402
    file_hash,
    load_json,
)


REQUEST_PATH = (
    HERE / "execution_authorization_request_e2_variability_r2_r3_v1.json"
)
ANALYZER_PATH = HERE / "analyze_e2_variability_r1_r3.py"


def validate_opening_sources() -> dict[str, Any]:
    config = load_json(runner.CONFIG_PATH)
    request = load_json(REQUEST_PATH)
    runner.validate_static_bindings(config)
    if runner.AUTHORIZATION_PATH.exists():
        raise ValueError("unexpected CF-08 E2 variability authorization file")
    if request["status"] != "awaiting_explicit_user_authorization":
        raise ValueError("variability authorization request must remain pending")
    if request["external_api_execution_authorized"] is not False:
        raise ValueError("opening package cannot authorize API execution")
    if request["model_execution_count"] != 0:
        raise ValueError("opening package must have zero model executions")
    if config["execution_status"] != "prepared_not_authorized":
        raise ValueError("variability config must remain unauthorized")
    expected_hashes = {
        "run_config_sha256": runner.CONFIG_PATH,
        "runner_sha256": Path(runner.__file__),
        "analyzer_sha256": ANALYZER_PATH,
        "validation_manifest_sha256": base.VALIDATION_MANIFEST_PATH,
        "r1_run_manifest_sha256": runner.R1_RUN_MANIFEST_PATH,
        "r1_analysis_manifest_sha256": runner.R1_ANALYSIS_MANIFEST_PATH,
    }
    for field, path in expected_hashes.items():
        if request[field] != file_hash(path):
            raise ValueError(f"variability opening hash mismatch: {field}")
    validation_manifest = load_json(base.VALIDATION_MANIFEST_PATH)
    task_artifact = next(
        row
        for row in validation_manifest["artifacts"]
        if row["filename"] == "e2_validation_tasks_v1.json"
    )
    if task_artifact["sha256"] != request["task_source_sha256"]:
        raise ValueError("variability task source binding mismatch")
    r1_report = load_json(runner.R1_RUN_REPORT_PATH)
    r1_analysis = load_json(runner.R1_ANALYSIS_REPORT_PATH)
    if r1_report["summary"]["status"] != "completed":
        raise ValueError("R1 source run is incomplete")
    if r1_report["summary"]["cell_count"] != 80:
        raise ValueError("R1 source cell count mismatch")
    if r1_analysis["status"] != "completed":
        raise ValueError("R1 source analysis is incomplete")
    if r1_analysis["interpretation_limits"]["model_run_repeats"] != 1:
        raise ValueError("R1 source repeat count mismatch")
    return {
        "config": config,
        "request": request,
        "validation_manifest": validation_manifest,
        "r1_report": r1_report,
        "r1_analysis": r1_analysis,
    }


def build_package(output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    values = validate_opening_sources()
    output_dir.mkdir(parents=True)
    snapshots = {
        runner.CONFIG_PATH: output_dir / "run_config_snapshot.json",
        Path(runner.__file__): output_dir / "runner_snapshot.py",
        ANALYZER_PATH: output_dir / "analyzer_snapshot.py",
        REQUEST_PATH: output_dir / "authorization_request_snapshot.json",
        base.VALIDATION_MANIFEST_PATH: (
            output_dir / "validation_candidate_manifest_snapshot.json"
        ),
        runner.R1_RUN_MANIFEST_PATH: output_dir / "r1_run_manifest_snapshot.json",
        runner.R1_RUN_REPORT_PATH: output_dir / "r1_run_report_snapshot.json",
        runner.R1_ANALYSIS_MANIFEST_PATH: (
            output_dir / "r1_analysis_manifest_snapshot.json"
        ),
        runner.R1_ANALYSIS_REPORT_PATH: (
            output_dir / "r1_analysis_report_snapshot.json"
        ),
    }
    for source, target in snapshots.items():
        shutil.copyfile(source, target)
    report = {
        "schema_version": "1.0-candidate",
        "candidate_id": "CF08-E2-VARIABILITY-R2-R3-OPENING-V1-20260803",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "prepared_not_authorized",
        "dataset_id": values["config"]["dataset_id"],
        "task_count": values["config"]["task_count"],
        "condition_count": values["config"]["condition_count"],
        "repeat_ids": values["config"]["repeat_ids"],
        "additional_repeat_count": values["config"][
            "additional_repeat_count"
        ],
        "total_repeat_count_after_execution": values["config"][
            "total_repeat_count_after_execution"
        ],
        "model_cell_count": values["config"]["authorized_model_cell_count"],
        "conditions": [
            row["condition_id"] for row in values["config"]["conditions"]
        ],
        "r1_source_run_id": values["r1_report"]["run_id"],
        "opened_validation_reuse": "variability_estimation_only",
        "repeat_units_are_independent_tasks": False,
        "held_out_task_content_copied_into_opening": False,
        "held_out_task_content_read_by_builder": False,
        "external_api_execution_authorized": False,
        "external_api_calls": 0,
        "gold_labels_sent": False,
        "mutation_history_sent": False,
        "tool_access": "disabled",
        "post_validation_policy_revision_allowed": False,
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
            "run_config_sha256": file_hash(runner.CONFIG_PATH),
            "runner_sha256": file_hash(Path(runner.__file__)),
            "analyzer_sha256": file_hash(ANALYZER_PATH),
            "authorization_request_sha256": file_hash(REQUEST_PATH),
            "validation_manifest_sha256": file_hash(
                base.VALIDATION_MANIFEST_PATH
            ),
            "r1_run_manifest_sha256": file_hash(
                runner.R1_RUN_MANIFEST_PATH
            ),
            "r1_analysis_manifest_sha256": file_hash(
                runner.R1_ANALYSIS_MANIFEST_PATH
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
        "repeat_units_are_independent_tasks": False,
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
