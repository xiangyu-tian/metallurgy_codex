"""Combine E2 R1-R3 and estimate model-run variability descriptively."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from core_freeze.e2_contract_boundaries import (  # noqa: E402
    analyze_e2_independent_validation as r1_analysis,
)
from core_freeze.e2_contract_boundaries.run_e2_development import (  # noqa: E402
    file_hash,
)
from core_freeze.e2_contract_boundaries.run_e2_independent_validation import (  # noqa: E402
    CONDITION_ORDER,
)


def _load_records(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _predicted_flags(record: dict[str, Any]) -> list[str]:
    if record["condition"] == "flags_only_v1_1":
        return record.get("predicted_flags") or []
    return record.get("merged_flags") or []


def _flags_exact(record: dict[str, Any]) -> bool:
    if record["condition"] == "flags_only_v1_1":
        return bool(record.get("flags_exact"))
    return bool(record.get("merged_flags_exact"))


def analyze_variability(
    r1_records: list[dict[str, Any]],
    r2_r3_records: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(r1_records) != 80:
        raise ValueError("R1 must contain 80 records")
    if len(r2_r3_records) != 160:
        raise ValueError("R2/R3 must contain 160 records")
    records = r1_records + r2_r3_records
    expected_repeats = {1, 2, 3}
    if {row["model_run_repeat"] for row in records} != expected_repeats:
        raise ValueError("combined E2 records must contain R1, R2 and R3")
    task_ids = sorted({row["task_id"] for row in records})
    if len(task_ids) != 40:
        raise ValueError("combined E2 records must contain 40 tasks")
    by_key = {
        (row["task_id"], row["condition"], row["model_run_repeat"]): row
        for row in records
    }
    expected_keys = {
        (task_id, condition, repeat_id)
        for task_id in task_ids
        for condition in CONDITION_ORDER
        for repeat_id in expected_repeats
    }
    if set(by_key) != expected_keys:
        raise ValueError("combined E2 repeat pairing is incomplete")
    repeat_metrics = {}
    for repeat_id in sorted(expected_repeats):
        subset = [
            row for row in records if row["model_run_repeat"] == repeat_id
        ]
        result = r1_analysis.analyze_records(subset)
        repeat_metrics[str(repeat_id)] = {
            "condition_metrics": result["condition_metrics"],
            "paired_summary": result["paired_summary"],
        }
    stability_rows = []
    for task_id in task_ids:
        for condition in CONDITION_ORDER:
            rows = [
                by_key[(task_id, condition, repeat_id)]
                for repeat_id in sorted(expected_repeats)
            ]
            flag_signatures = [
                tuple(sorted(_predicted_flags(row))) for row in rows
            ]
            actions = [row.get("predicted_action") for row in rows]
            exact_values = [_flags_exact(row) for row in rows]
            action_correct_values = [
                bool(row.get("action_correct")) for row in rows
            ]
            stability_rows.append(
                {
                    "task_id": task_id,
                    "condition": condition,
                    "flag_prediction_stable": len(set(flag_signatures)) == 1,
                    "action_prediction_stable": len(set(actions)) == 1,
                    "flags_exact_outcome_stable": len(set(exact_values)) == 1,
                    "action_correct_outcome_stable": (
                        len(set(action_correct_values)) == 1
                    ),
                    "flag_signatures": [list(value) for value in flag_signatures],
                    "predicted_actions": actions,
                    "flags_exact": exact_values,
                    "action_correct": action_correct_values,
                }
            )
    stability_summary = {}
    for condition in CONDITION_ORDER:
        subset = [
            row for row in stability_rows if row["condition"] == condition
        ]
        stability_summary[condition] = {
            "task_count": len(subset),
            "flag_prediction_stable_count": sum(
                row["flag_prediction_stable"] for row in subset
            ),
            "action_prediction_stable_count": sum(
                row["action_prediction_stable"] for row in subset
            ),
            "flags_exact_outcome_stable_count": sum(
                row["flags_exact_outcome_stable"] for row in subset
            ),
            "action_correct_outcome_stable_count": sum(
                row["action_correct_outcome_stable"] for row in subset
            ),
        }
    return {
        "repeat_metrics": repeat_metrics,
        "stability_summary": stability_summary,
        "stability_rows": stability_rows,
        "analysis_policy": {
            "repeat_units_are_independent_tasks": False,
            "task_is_resampling_cluster": True,
            "post_validation_policy_revision_allowed": False,
            "confirmatory_inference_allowed": False,
        },
    }


def write_analysis(
    r1_run_dir: Path,
    r2_r3_run_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    r1_records_path = r1_run_dir / "run_records.jsonl"
    extra_records_path = r2_r3_run_dir / "run_records.jsonl"
    result = analyze_variability(
        _load_records(r1_records_path),
        _load_records(extra_records_path),
    )
    output_dir.mkdir(parents=True)
    metrics_path = output_dir / "repeat_metrics.json"
    metrics_path.write_text(
        json.dumps(result["repeat_metrics"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    stability_path = output_dir / "stability_by_task.jsonl"
    stability_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in result["stability_rows"]
        ),
        encoding="utf-8",
    )
    report = {
        "schema_version": "1.0-candidate",
        "analysis_id": "CF08-E2-VARIABILITY-R1-R3-V1-20260803",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "stability_summary": result["stability_summary"],
        "analysis_policy": result["analysis_policy"],
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    report_path = output_dir / "variability_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    artifacts = [metrics_path, stability_path, report_path]
    manifest = {
        "schema_version": "1.0-candidate",
        "analysis_id": report["analysis_id"],
        "source_bindings": {
            "r1_records_sha256": file_hash(r1_records_path),
            "r2_r3_records_sha256": file_hash(extra_records_path),
            "analyzer_sha256": file_hash(Path(__file__)),
        },
        "artifacts": [
            {"filename": path.name, "sha256": file_hash(path)}
            for path in artifacts
        ],
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
    parser.add_argument("--r1-run-dir", type=Path, required=True)
    parser.add_argument("--r2-r3-run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = write_analysis(
        args.r1_run_dir.resolve(),
        args.r2_r3_run_dir.resolve(),
        args.output_dir.resolve(),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
