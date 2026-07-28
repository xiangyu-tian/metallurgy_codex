"""Finalize CF-11 after immutable analysis and governed review records exist."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


REQUIRED_COMPONENTS = {
    "design_specification": "passed",
    "estimand_definition": "passed",
    "sensitivity_specification": "passed",
    "engine_implementation": "passed",
    "synthetic_integration": "passed",
    "artifact_contract": "passed",
    "finalization_implementation": "passed",
}
REVIEW_TYPES = {
    "candidate_evidence": {
        "record_type": "real_candidate_dry_run",
        "decision_field": "status",
        "decision": "passed",
        "reviewer_role": "experiment_executor",
    },
    "statistics_review": {
        "record_type": "statistical_review",
        "decision_field": "decision",
        "decision": "approved",
        "reviewer_role": "statistics_reviewer",
    },
    "report_review": {
        "record_type": "report_review",
        "decision_field": "decision",
        "decision": "approved",
        "reviewer_role": "report_reviewer",
    },
    "approval": {
        "record_type": "project_approval",
        "decision_field": "decision",
        "decision": "approved",
        "reviewer_role": "project_approver",
    },
}
GOVERNANCE_MODE = "protected_repository_review"


class FinalizationError(ValueError):
    """Raised when CF-11 finalization evidence is incomplete or inconsistent."""


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FinalizationError(f"cannot read JSON evidence: {path}") from error
    if not isinstance(value, dict):
        raise FinalizationError(f"JSON evidence must be an object: {path}")
    return value


def _require_hash(value: Any, label: str, lengths: set[int]) -> str:
    if (
        not isinstance(value, str)
        or len(value) not in lengths
        or any(character not in "0123456789abcdefABCDEF" for character in value)
    ):
        raise FinalizationError(f"{label} is not a valid hexadecimal hash")
    return value.lower()


def _read_manifest(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as error:
        raise FinalizationError(f"cannot read artifact manifest: {path}") from error
    if not rows or set(rows[0]) != {"filename", "sha256"}:
        raise FinalizationError("artifact manifest has an invalid schema")
    return rows


def _resolve_artifact(analysis_root: Path, filename: Any) -> Path:
    if not isinstance(filename, str) or not filename.strip():
        raise FinalizationError("manifest filename must be a non-empty string")
    windows_path = PureWindowsPath(filename)
    posix_path = PurePosixPath(filename)
    if (
        windows_path.is_absolute()
        or posix_path.is_absolute()
        or windows_path.drive
        or ".." in windows_path.parts
        or ".." in posix_path.parts
    ):
        raise FinalizationError(
            f"manifest filename escapes analysis directory: {filename}"
        )
    try:
        resolved = (analysis_root / filename).resolve(strict=True)
        resolved.relative_to(analysis_root)
    except (OSError, ValueError) as error:
        raise FinalizationError(
            f"manifest filename escapes analysis directory: {filename}"
        ) from error
    if not resolved.is_file():
        raise FinalizationError(f"missing artifact: {filename}")
    return resolved


def _validate_analysis(analysis_dir: Path) -> dict[str, Any]:
    try:
        analysis_root = analysis_dir.resolve(strict=True)
    except OSError as error:
        raise FinalizationError(
            f"analysis directory does not exist: {analysis_dir}"
        ) from error
    if not analysis_root.is_dir():
        raise FinalizationError(f"analysis path is not a directory: {analysis_dir}")
    report_path = _resolve_artifact(
        analysis_root,
        "confirmatory_report.json",
    )
    manifest_path = _resolve_artifact(
        analysis_root,
        "artifact_manifest.csv",
    )
    report = _read_json(report_path)
    manifest_rows = _read_manifest(manifest_path)

    manifest_files = {row["filename"] for row in manifest_rows}
    if len(manifest_files) != len(manifest_rows):
        raise FinalizationError("artifact manifest contains duplicate filenames")
    expected_files = set(report.get("artifact_files", [])) - {
        "artifact_manifest.csv"
    }
    if manifest_files != expected_files:
        raise FinalizationError("manifest and report artifact sets do not match")
    resolved_artifacts: set[str] = set()
    for row in manifest_rows:
        artifact = _resolve_artifact(analysis_root, row["filename"])
        canonical = str(artifact).casefold()
        if canonical in resolved_artifacts:
            raise FinalizationError(
                "artifact manifest resolves multiple names to one file"
            )
        resolved_artifacts.add(canonical)
        expected_hash = _require_hash(
            row["sha256"],
            f"manifest hash for {row['filename']}",
            {64},
        )
        if _sha256(artifact) != expected_hash:
            raise FinalizationError(f"artifact hash mismatch: {row['filename']}")

    _require_hash(report.get("input_hash"), "input_hash", {64})
    _require_hash(report.get("r_engine_lock_hash"), "r_engine_lock_hash", {64})
    _require_hash(report.get("analysis_commit"), "analysis_commit", {40, 64})
    if report.get("tracked_worktree_clean") is not True:
        raise FinalizationError(
            "analysis was not produced from a clean tracked worktree"
        )
    if report.get("cf11_status") != "in_progress":
        raise FinalizationError("analysis report must remain in_progress")
    for component, expected in REQUIRED_COMPONENTS.items():
        actual = report.get("cf11_components", {}).get(component)
        if actual != expected:
            raise FinalizationError(
                f"analysis component {component} must be {expected}"
            )
    model_statuses = report.get("model_statuses", {})
    for primary in ("h3", "h4"):
        if model_statuses.get(primary) != "converged":
            raise FinalizationError(f"primary model {primary} did not converge")
    for sensitivity in (
        "h3_schema_adjusted_sensitivity",
        "h3_method_interaction_sensitivity",
        "h4_schema_adjusted_sensitivity",
    ):
        if model_statuses.get(sensitivity) not in {"converged", "failed"}:
            raise FinalizationError(
                f"sensitivity model status is missing: {sensitivity}"
            )
    return report


def _parse_aware_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise FinalizationError(f"{label} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise FinalizationError(
            f"{label} must be an ISO-8601 timestamp"
        ) from error
    if parsed.utcoffset() is None:
        raise FinalizationError(f"{label} must include a timezone offset")
    return parsed


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FinalizationError(f"{label} is required")
    return value.strip()


def _validate_evidence(
    label: str,
    evidence: dict[str, Any],
    report: dict[str, Any],
    manifest_hash: str,
) -> tuple[dict[str, Any], datetime]:
    contract = REVIEW_TYPES[label]
    expected_type = contract["record_type"]
    if evidence.get("record_type") != expected_type:
        raise FinalizationError(f"{label}.record_type must be {expected_type}")
    if evidence.get("governance_mode") != GOVERNANCE_MODE:
        raise FinalizationError(
            f"{label}.governance_mode must be {GOVERNANCE_MODE}"
        )
    decision_field = contract["decision_field"]
    expected_decision = contract["decision"]
    if evidence.get(decision_field) != expected_decision:
        raise FinalizationError(
            f"{label}.{decision_field} must be {expected_decision}"
        )
    if evidence.get("input_hash") != report["input_hash"]:
        raise FinalizationError(f"{label}.input_hash does not match analysis")
    if evidence.get("analysis_commit") != report["analysis_commit"]:
        raise FinalizationError(
            f"{label}.analysis_commit does not match analysis"
        )
    if evidence.get("artifact_manifest_hash") != manifest_hash:
        raise FinalizationError(
            f"{label}.artifact_manifest_hash does not match analysis"
        )
    reviewer = _require_text(evidence.get("reviewer"), f"{label}.reviewer")
    reviewer_role = _require_text(
        evidence.get("reviewer_role"),
        f"{label}.reviewer_role",
    )
    if reviewer_role != contract["reviewer_role"]:
        raise FinalizationError(
            f"{label}.reviewer_role must be {contract['reviewer_role']}"
        )
    organization = _require_text(
        evidence.get("organization_or_team"),
        f"{label}.organization_or_team",
    )
    review_scope = _require_text(
        evidence.get("review_scope"),
        f"{label}.review_scope",
    )
    recorded_at_text = _require_text(
        evidence.get("recorded_at"),
        f"{label}.recorded_at",
    )
    recorded_at = _parse_aware_time(
        recorded_at_text,
        f"{label}.recorded_at",
    )
    record = {
        "record_type": expected_type,
        "governance_mode": GOVERNANCE_MODE,
        "reviewer": reviewer,
        "reviewer_role": reviewer_role,
        "organization_or_team": organization,
        "review_scope": review_scope,
        "recorded_at": recorded_at_text,
        "decision": expected_decision,
        "evidence_hash": hashlib.sha256(
            json.dumps(
                evidence,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }
    return record, recorded_at


def finalize_cf11(
    analysis_dir: str | Path,
    *,
    candidate_evidence: str | Path,
    statistics_review: str | Path,
    report_review: str | Path,
    approval: str | Path,
    output: str | Path,
) -> dict[str, Any]:
    analysis_root = Path(analysis_dir).resolve()
    report = _validate_analysis(analysis_root)
    manifest_hash = _sha256(analysis_root / "artifact_manifest.csv")
    analysis_generated_at = _parse_aware_time(
        report.get("generated_at"),
        "analysis.generated_at",
    )
    evidence_paths = {
        "candidate_evidence": candidate_evidence,
        "statistics_review": statistics_review,
        "report_review": report_review,
        "approval": approval,
    }
    validated: dict[str, dict[str, Any]] = {}
    recorded_times: dict[str, datetime] = {}
    for label, path in evidence_paths.items():
        record, recorded_at = _validate_evidence(
            label,
            _read_json(path),
            report,
            manifest_hash,
        )
        validated[label] = record
        recorded_times[label] = recorded_at

    candidate_time = recorded_times["candidate_evidence"]
    statistics_time = recorded_times["statistics_review"]
    report_time = recorded_times["report_review"]
    approval_time = recorded_times["approval"]
    if candidate_time < analysis_generated_at:
        raise FinalizationError(
            "candidate evidence must be recorded after analysis generation"
        )
    if statistics_time < candidate_time or report_time < candidate_time:
        raise FinalizationError(
            "statistics and report reviews must follow candidate evidence"
        )
    if approval_time < max(statistics_time, report_time):
        raise FinalizationError(
            "project approval must follow statistics and report reviews"
        )

    statistics_reviewer = validated["statistics_review"]["reviewer"].casefold()
    project_approver = validated["approval"]["reviewer"].casefold()
    if statistics_reviewer == project_approver:
        raise FinalizationError(
            "statistics reviewer and project approver must be different people"
        )
    components = {
        **REQUIRED_COMPONENTS,
        "artifact_contract": "passed",
        "real_candidate_dry_run": "passed",
        "statistical_review": "passed",
        "report_review": "passed",
        "approval": "passed",
        "overall": "passed",
    }
    analysis_report_hash = _sha256(
        analysis_root / "confirmatory_report.json"
    )
    identity_material = {
        "analysis_report_hash": analysis_report_hash,
        "artifact_manifest_hash": manifest_hash,
        "evidence_hashes": {
            label: evidence["evidence_hash"]
            for label, evidence in sorted(validated.items())
        },
    }
    finalization_id = "CF11-" + hashlib.sha256(
        json.dumps(
            identity_material,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:20].upper()
    record = {
        "record_version": "1.1",
        "record_type": "cf11_finalization",
        "finalization_id": finalization_id,
        "generated_at": datetime.now().astimezone().isoformat(),
        "analysis_commit": report["analysis_commit"],
        "input_hash": report["input_hash"],
        "analysis_report_hash": analysis_report_hash,
        "artifact_manifest_hash": manifest_hash,
        "governance_mode": GOVERNANCE_MODE,
        "evidence_assurance": (
            "repository_governed_records_not_cryptographic_signatures"
        ),
        "cf11_components": components,
        "reviews": validated,
        "cf11_status": "passed",
        "core_frozen": False,
        "core_frozen_note": (
            "CF-11 passed does not imply CF-01 through CF-10 passed."
        ),
    }
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    except FileExistsError as error:
        raise FinalizationError(
            f"finalization output already exists and cannot be replaced: {output}"
        ) from error
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("analysis_dir", type=Path)
    parser.add_argument("--candidate-evidence", type=Path, required=True)
    parser.add_argument("--statistics-review", type=Path, required=True)
    parser.add_argument("--report-review", type=Path, required=True)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    record = finalize_cf11(
        args.analysis_dir,
        candidate_evidence=args.candidate_evidence,
        statistics_review=args.statistics_review,
        report_review=args.report_review,
        approval=args.approval,
        output=args.output,
    )
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
