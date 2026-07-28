"""Finalize CF-11 only after immutable analysis and signed reviews exist."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_COMPONENTS = {
    "design_specification": "passed",
    "estimand_definition": "passed",
    "sensitivity_specification": "passed",
    "engine_implementation": "passed",
    "synthetic_integration": "passed",
    "artifact_contract": "passed",
}
REVIEW_TYPES = {
    "candidate_evidence": ("real_candidate_dry_run", "passed"),
    "statistics_review": ("statistical_review", "approved"),
    "report_review": ("report_review", "approved"),
    "approval": ("project_approval", "approved"),
}


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


def _validate_analysis(analysis_dir: Path) -> dict[str, Any]:
    report_path = analysis_dir / "confirmatory_report.json"
    manifest_path = analysis_dir / "artifact_manifest.csv"
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
    for row in manifest_rows:
        artifact = analysis_dir / row["filename"]
        if not artifact.is_file():
            raise FinalizationError(f"missing artifact: {row['filename']}")
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


def _validate_signature_time(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise FinalizationError(f"{label}.signed_at is required")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise FinalizationError(
            f"{label}.signed_at must be an ISO-8601 timestamp"
        ) from error
    return value


def _validate_evidence(
    label: str,
    evidence: dict[str, Any],
    report: dict[str, Any],
    manifest_hash: str,
) -> dict[str, Any]:
    expected_type, expected_decision = REVIEW_TYPES[label]
    if evidence.get("record_type") != expected_type:
        raise FinalizationError(f"{label}.record_type must be {expected_type}")
    decision_field = "status" if label == "candidate_evidence" else "decision"
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
    reviewer = evidence.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise FinalizationError(f"{label}.reviewer is required")
    signed_at = _validate_signature_time(evidence.get("signed_at"), label)
    return {
        "record_type": expected_type,
        "reviewer": reviewer.strip(),
        "signed_at": signed_at,
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


def finalize_cf11(
    analysis_dir: str | Path,
    *,
    candidate_evidence: str | Path,
    statistics_review: str | Path,
    report_review: str | Path,
    approval: str | Path,
    output: str | Path,
) -> dict[str, Any]:
    analysis_root = Path(analysis_dir)
    report = _validate_analysis(analysis_root)
    manifest_hash = _sha256(analysis_root / "artifact_manifest.csv")
    evidence_paths = {
        "candidate_evidence": candidate_evidence,
        "statistics_review": statistics_review,
        "report_review": report_review,
        "approval": approval,
    }
    validated = {
        label: _validate_evidence(
            label,
            _read_json(path),
            report,
            manifest_hash,
        )
        for label, path in evidence_paths.items()
    }
    components = {
        **REQUIRED_COMPONENTS,
        "artifact_contract": "passed",
        "real_candidate_dry_run": "passed",
        "statistical_review": "passed",
        "report_review": "passed",
        "approval": "passed",
        "overall": "passed",
    }
    record = {
        "record_version": "1.0",
        "record_type": "cf11_finalization",
        "generated_at": datetime.now().astimezone().isoformat(),
        "analysis_commit": report["analysis_commit"],
        "input_hash": report["input_hash"],
        "analysis_report_hash": _sha256(
            analysis_root / "confirmatory_report.json"
        ),
        "artifact_manifest_hash": manifest_hash,
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
    output_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
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
