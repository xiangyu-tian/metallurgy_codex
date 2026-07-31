"""Analyze an E2 development run without changing its strict score."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def jaccard(left: list[str], right: list[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    return len(left_set & right_set) / len(left_set | right_set)


def decision_from_flags(
    flags: list[str],
    policy: dict[str, Any],
) -> tuple[str, str]:
    flag_set = set(flags)
    for rule in policy["priority"]:
        if not rule["any_flags"] or flag_set & set(rule["any_flags"]):
            return rule["primary_status"], rule["policy_expected_action"]
    raise ValueError("policy priority has no ready fallback")


def inspect_record(
    record: dict[str, Any],
    *,
    output_schema: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    try:
        parsed = json.loads(record["raw_output"])
    except (TypeError, json.JSONDecodeError):
        parsed = None
    allowed_flags = set(
        output_schema["properties"]["flags"]["items"]["enum"]
    )
    allowed_actions = set(output_schema["properties"]["action"]["enum"])
    allowed_primary = set(
        output_schema["properties"]["primary_status"]["enum"]
    )
    flags = parsed.get("flags") if isinstance(parsed, dict) else None
    flags_well_formed = (
        isinstance(flags, list)
        and all(isinstance(flag, str) for flag in flags)
        and len(flags) == len(set(flags))
        and set(flags) <= allowed_flags
    )
    action = parsed.get("action") if isinstance(parsed, dict) else None
    primary = (
        parsed.get("primary_status") if isinstance(parsed, dict) else None
    )
    action_well_formed = action in allowed_actions
    primary_well_formed = primary in allowed_primary
    predicted_flags = flags if flags_well_formed else []
    derived_primary, derived_action = decision_from_flags(
        predicted_flags,
        policy,
    )
    expected_flags = record["expected_flags"]
    flags_exact = flags_well_formed and (
        set(predicted_flags) == set(expected_flags)
    )
    error_types: list[str] = []
    if not record["schema_valid"]:
        error_types.append("strict_schema_invalid")
    if (
        flags_well_formed
        and action_well_formed
        and not primary_well_formed
    ):
        error_types.append("primary_status_mapping_error")
    if not flags_exact:
        error_types.append("flags_mismatch")
    if not action_well_formed or action != record["expected_action"]:
        error_types.append("action_mismatch")
    return {
        "task_id": record["task_id"],
        "source_tool_id": record["source_tool_id"],
        "mutation_types": "+".join(record["mutation_types"]) or "ready",
        "expected_flags": "|".join(sorted(expected_flags)),
        "predicted_flags": (
            "|".join(sorted(predicted_flags))
            if flags_well_formed
            else "__INVALID__"
        ),
        "expected_primary_status": record["expected_primary_status"],
        "raw_primary_status": primary,
        "derived_primary_status": derived_primary,
        "expected_action": record["expected_action"],
        "raw_action": action,
        "derived_action": derived_action,
        "strict_schema_valid": bool(record["schema_valid"]),
        "flags_well_formed": flags_well_formed,
        "action_well_formed": action_well_formed,
        "primary_status_well_formed": primary_well_formed,
        "flags_exact": flags_exact,
        "flags_jaccard": (
            jaccard(predicted_flags, expected_flags)
            if flags_well_formed
            else 0.0
        ),
        "raw_action_correct": (
            action_well_formed and action == record["expected_action"]
        ),
        "derived_primary_correct": (
            derived_primary == record["expected_primary_status"]
        ),
        "derived_action_correct": (
            derived_action == record["expected_action"]
        ),
        "error_types": "|".join(error_types) or "none",
    }


def _rate(rows: list[dict[str, Any]], field: str) -> float | None:
    if not rows:
        return None
    return sum(bool(row[field]) for row in rows) / len(rows)


def build_analysis(
    records: list[dict[str, Any]],
    *,
    run_report: dict[str, Any],
    output_schema: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    completed = [row for row in records if row["status"] == "completed"]
    diagnostics = [
        inspect_record(
            row,
            output_schema=output_schema,
            policy=policy,
        )
        for row in completed
    ]
    by_mutation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in diagnostics:
        by_mutation[row["mutation_types"]].append(row)
    mutation_summary = []
    for mutation, rows in sorted(by_mutation.items()):
        mutation_summary.append(
            {
                "mutation_types": mutation,
                "task_count": len(rows),
                "strict_schema_valid_rate": _rate(
                    rows, "strict_schema_valid"
                ),
                "flags_exact_accuracy": _rate(rows, "flags_exact"),
                "raw_action_accuracy": _rate(rows, "raw_action_correct"),
                "derived_primary_accuracy": _rate(
                    rows, "derived_primary_correct"
                ),
                "derived_action_accuracy": _rate(
                    rows, "derived_action_correct"
                ),
            }
        )
    error_counts = Counter()
    for row in diagnostics:
        for error_type in row["error_types"].split("|"):
            if error_type != "none":
                error_counts[error_type] += 1
    parsed_diagnostic = {
        "task_count": len(diagnostics),
        "flags_well_formed_rate": _rate(
            diagnostics, "flags_well_formed"
        ),
        "action_well_formed_rate": _rate(
            diagnostics, "action_well_formed"
        ),
        "primary_status_well_formed_rate": _rate(
            diagnostics, "primary_status_well_formed"
        ),
        "flags_exact_count": sum(row["flags_exact"] for row in diagnostics),
        "flags_exact_accuracy": _rate(diagnostics, "flags_exact"),
        "mean_flags_jaccard": (
            sum(row["flags_jaccard"] for row in diagnostics)
            / len(diagnostics)
            if diagnostics
            else None
        ),
        "raw_action_correct_count": sum(
            row["raw_action_correct"] for row in diagnostics
        ),
        "raw_action_accuracy": _rate(
            diagnostics, "raw_action_correct"
        ),
        "derived_primary_accuracy": _rate(
            diagnostics, "derived_primary_correct"
        ),
        "derived_action_accuracy": _rate(
            diagnostics, "derived_action_correct"
        ),
        "error_counts": dict(sorted(error_counts.items())),
    }
    analysis = {
        "schema_version": "1.0",
        "analysis_id": "E2-DEVELOPMENT-DIAGNOSTIC-V1-20260731",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_report["run_id"],
        "run_config_id": run_report["run_config_id"],
        "dataset_id": run_report["dataset_id"],
        "strict_score_unchanged": True,
        "strict_summary": run_report["summary"],
        "parsed_field_diagnostic": parsed_diagnostic,
        "interpretation": {
            "primary_observation": (
                "All completed responses were parseable JSON, but many used "
                "a fine-grained flag as primary_status instead of the "
                "predefined aggregate status."
            ),
            "secondary_observation": (
                "Remaining semantic errors concentrate in unsupported-system "
                "distinction and multi-label retention/priority."
            ),
            "diagnostic_not_official_rescore": True,
            "model_policy_revision_allowed_by_run": bool(
                run_report.get("model_policy_revision_allowed")
            ),
            "confirmatory_inference_allowed": False,
            "core_frozen": False,
        },
    }
    return diagnostics, mutation_summary, analysis


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty CSV: {path.name}")
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(
    *,
    output_dir: Path,
    source_dir: Path,
    diagnostics: list[dict[str, Any]],
    mutation_summary: list[dict[str, Any]],
    analysis: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    diagnostics_path = output_dir / "task_diagnostics.csv"
    mutations_path = output_dir / "mutation_summary.csv"
    report_path = output_dir / "analysis_report.json"
    write_csv(diagnostics_path, diagnostics)
    write_csv(mutations_path, mutation_summary)
    report_path.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    artifacts = [
        {
            "filename": path.name,
            "sha256": file_hash(path),
        }
        for path in (diagnostics_path, mutations_path, report_path)
    ]
    manifest = {
        "schema_version": "1.0",
        "analysis_id": analysis["analysis_id"],
        "source_bindings": {
            "source_directory": source_dir.name,
            "run_records_sha256": file_hash(
                source_dir / "run_records.jsonl"
            ),
            "run_report_sha256": file_hash(source_dir / "run_report.json"),
            "source_manifest_sha256": file_hash(
                source_dir / "artifact_manifest.json"
            ),
            "analysis_script_sha256": file_hash(Path(__file__)),
        },
        "artifacts": artifacts,
        "strict_score_unchanged": True,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    (output_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source_dir = args.source_dir.resolve()
    run_report = load_json(source_dir / "run_report.json")
    records = load_jsonl(source_dir / "run_records.jsonl")
    output_schema = load_json(
        source_dir / "output_schema_snapshot.json"
    )
    policy = load_json(source_dir / "policy_snapshot.json")
    diagnostics, mutation_summary, analysis = build_analysis(
        records,
        run_report=run_report,
        output_schema=output_schema,
        policy=policy,
    )
    write_outputs(
        output_dir=args.output_dir.resolve(),
        source_dir=source_dir,
        diagnostics=diagnostics,
        mutation_summary=mutation_summary,
        analysis=analysis,
    )
    print(
        json.dumps(
            analysis["parsed_field_diagnostic"],
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
