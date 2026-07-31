"""Finalize the approved E1b design without overclaiming global CF-08/CF-09."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
CF08_DIR = PROJECT_ROOT / "outputs" / "v11_cf08_power_20260731"
CF08_REPORT_PATH = CF08_DIR / "cf08_power_report.json"
CF08_MANIFEST_PATH = CF08_DIR / "artifact_manifest.json"
APPROVAL_PATH = (
    HERE / "approvals" / "v11_cf08_e1b_approval_20260731.json"
)
ADDENDUM_PATH = (
    PROJECT_ROOT
    / "docs"
    / "experiments"
    / "sample_size_addendum_v1.1-rc1.md"
)

APPROVED_PARAMETER_KEYS = (
    "minimum_meaningful_accuracy_gain",
    "alpha",
    "test_direction",
    "target_power",
    "pilot_uncertainty_inflation",
    "base_task_groups",
    "base_task_groups_per_verified_tool_family",
    "tasks_per_base_task_group",
    "task_count",
    "condition_count",
    "model_run_repeats",
    "paired_repeat_count",
    "model_cell_count",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def validate_approval(
    report: dict[str, Any],
    approval: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if report.get("status") != "in_progress":
        errors.append("CF-08 candidate report must remain in_progress")
    if report.get("candidate_status") != "ready_for_review":
        errors.append("CF-08 candidate is not ready_for_review")
    if approval.get("decision") != "approved":
        errors.append("approval decision is not approved")
    if approval.get("approved_scope") != "E1b formal benefit experiment only":
        errors.append("approval scope is not limited to E1b")
    if approval.get("artifact_manifest_sha256") != file_hash(
        CF08_MANIFEST_PATH
    ):
        errors.append("CF-08 manifest hash does not match approval")
    if approval.get("cf08_power_report_sha256") != file_hash(
        CF08_REPORT_PATH
    ):
        errors.append("CF-08 report hash does not match approval")
    approved_at = approval.get("approved_at")
    try:
        parsed_time = datetime.fromisoformat(approved_at)
        if parsed_time.utcoffset() is None:
            errors.append("approved_at must include a timezone")
    except (TypeError, ValueError):
        errors.append("approved_at is not valid ISO-8601")
    commit = approval.get("analysis_git_commit")
    if not isinstance(commit, str) or len(commit) != 40:
        errors.append("analysis_git_commit must be a full 40-character hash")

    candidate = report.get("recommended_candidate", {})
    approved = approval.get("approved_parameters", {})
    for key in APPROVED_PARAMETER_KEYS:
        if approved.get(key) != candidate.get(key):
            errors.append(
                f"approved parameter mismatch for {key}: "
                f"{approved.get(key)!r} != {candidate.get(key)!r}"
            )
    if candidate.get("approval_status") != "pending":
        errors.append("immutable candidate report must remain pending")
    if report.get("core_frozen") is not False:
        errors.append("candidate report must keep core_frozen=false")
    return errors


def validate_addendum() -> list[str]:
    text = ADDENDUM_PATH.read_text(encoding="utf-8")
    required_tokens = (
        "版本：`1.1-rc1`",
        "E1b工具收益",
        "base_task_groups: 120",
        "model_run_repeats: 3",
        "model_cell_count: 1440",
        "E1a Schema暴露",
        "CF-09：`in_progress`",
        "core_frozen: false",
    )
    return [
        f"sample-size addendum missing token: {token}"
        for token in required_tokens
        if token not in text
    ]


def run_finalization(output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    report = load_json(CF08_REPORT_PATH)
    approval = load_json(APPROVAL_PATH)
    errors = validate_approval(report, approval) + validate_addendum()
    if errors:
        raise ValueError("; ".join(errors))

    finalization = {
        "schema_version": "1.0",
        "finalization_id": "V11-CF08-CF09-E1B-FINAL-20260731",
        "approval_id": approval["approval_id"],
        "approved_at": approval["approved_at"],
        "approved_scope": approval["approved_scope"],
        "analysis_git_commit": approval["analysis_git_commit"],
        "source_bindings": {
            "cf08_manifest_sha256": file_hash(CF08_MANIFEST_PATH),
            "cf08_report_sha256": file_hash(CF08_REPORT_PATH),
            "approval_record_sha256": file_hash(APPROVAL_PATH),
            "sample_size_addendum_sha256": file_hash(ADDENDUM_PATH),
        },
        "approved_parameters": approval["approved_parameters"],
        "status_updates": {
            "cf03": {
                "e1b_candidate_evidence": "passed",
                "e1b_power_and_repeat_freeze": "passed",
                "overall": "passed",
            },
            "cf08": {
                "e1b_component": "passed",
                "e1a_component": "pending",
                "e2_component": "pending",
                "e3_component": "pending",
                "overall": "in_progress",
            },
            "cf09": {
                "e1b_component": "passed",
                "e1a_component": "pending",
                "e2_component": "pending",
                "e3_component": "pending",
                "overall": "in_progress",
            },
        },
        "approval_is_cryptographic_signature": False,
        "cf08_global_passed": False,
        "cf09_global_passed": False,
        "core_frozen": False,
    }
    coverage = {
        "schema_version": "1.0",
        "coverage_id": "V11-CF09-COVERAGE-20260731",
        "experiments": [
            {
                "experiment": "E1a",
                "sample_size_status": "pending",
                "repeat_count_status": "pending",
                "blocker": "Schema-condition pilot and effect variance unavailable",
            },
            {
                "experiment": "E1b",
                "sample_size_status": "approved",
                "repeat_count_status": "approved",
                "base_task_groups": 120,
                "task_count": 240,
                "model_run_repeats": 3,
                "model_cell_count": 1440,
            },
            {
                "experiment": "E2",
                "sample_size_status": "pending",
                "repeat_count_status": "pending",
                "blocker": "CF-04 mutation pilot unavailable",
            },
            {
                "experiment": "E3",
                "sample_size_status": "pending",
                "repeat_count_status": "pending",
                "blocker": "CF-05/CF-06 routing and API pilots unavailable",
            },
        ],
        "approved_experiment_count": 1,
        "required_experiment_count": 4,
        "cf09_status": "in_progress",
        "core_frozen": False,
    }

    output_dir.mkdir(parents=True)
    finalization_path = output_dir / "e1b_design_finalization.json"
    coverage_path = output_dir / "cf09_coverage_report.json"
    finalization_path.write_text(
        json.dumps(finalization, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    coverage_path.write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    sources = [
        CF08_REPORT_PATH,
        CF08_MANIFEST_PATH,
        APPROVAL_PATH,
        ADDENDUM_PATH,
        Path(__file__),
    ]
    manifest = {
        "schema_version": "1.0",
        "finalization_id": finalization["finalization_id"],
        "artifacts": [
            {
                "filename": path.name,
                "sha256": file_hash(path),
            }
            for path in (finalization_path, coverage_path)
        ],
        "source_artifacts": [
            {"filename": relative(path), "sha256": file_hash(path)}
            for path in sources
        ],
        "cf03_status": "passed",
        "cf08_status": "in_progress",
        "cf09_status": "in_progress",
        "core_frozen": False,
    }
    (output_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return finalization


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=(
            PROJECT_ROOT
            / "outputs"
            / "v11_cf08_cf09_e1b_final_20260731"
        ),
    )
    args = parser.parse_args()
    finalization = run_finalization(args.output_dir)
    print(
        json.dumps(
            {
                "finalization_id": finalization["finalization_id"],
                "status_updates": finalization["status_updates"],
                "core_frozen": finalization["core_frozen"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
