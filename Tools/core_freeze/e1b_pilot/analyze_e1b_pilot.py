"""Create a descriptive, task-clustered analysis of an E1b development run."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONDITIONS = ("no_tool", "forced_verified_oracle_parameters")
PROJECT_ROOT = Path(__file__).resolve().parent.parents[2]


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_relative(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT).as_posix()


def verify_manifest(run_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / "artifact_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = run_dir.resolve()
    errors = []
    for row in manifest.get("artifacts", []):
        relative = Path(row["filename"])
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(f"unsafe artifact path: {row['filename']}")
            continue
        artifact = (run_dir / relative).resolve()
        try:
            artifact.relative_to(root)
        except ValueError:
            errors.append(f"artifact escapes run directory: {row['filename']}")
            continue
        if not artifact.is_file():
            errors.append(f"missing artifact: {row['filename']}")
        elif file_hash(artifact) != row["sha256"]:
            errors.append(f"artifact hash mismatch: {row['filename']}")
    if errors:
        raise ValueError("; ".join(errors))
    return manifest


def load_records(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _condition_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if row["status"] == "completed"]
    usage_totals: dict[str, int | float] = defaultdict(int)
    for row in rows:
        usage = row.get("response_metadata", {}).get("usage") or {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                usage_totals[key] += value
    return {
        "cell_count": len(rows),
        "completed_count": len(completed),
        "correct_count": sum(bool(row["correct"]) for row in completed),
        "accuracy": (
            sum(bool(row["correct"]) for row in completed) / len(completed)
            if completed
            else None
        ),
        "parse_failure_count": sum(
            row.get("parse_status") != "parsed" for row in rows
        ),
        "status_counts": dict(
            sorted(Counter(row["status"] for row in rows).items())
        ),
        "usage_totals": dict(usage_totals),
        "mean_latency_ms": (
            sum(float(row["latency_ms"]) for row in rows) / len(rows)
            if rows
            else None
        ),
    }


def analyze_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_pair: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        by_condition[row["condition"]].append(row)
        by_pair[
            (row["task_id"], int(row["model_run_repeat"]))
        ][row["condition"]] = row
        by_task[row["task_id"]].append(row)

    condition_summary = {
        condition: _condition_summary(by_condition.get(condition, []))
        for condition in CONDITIONS
    }
    complete_pair_differences = []
    incomplete_pairs = []
    for (task_id, repeat), pair in sorted(by_pair.items()):
        if all(
            condition in pair and pair[condition]["status"] == "completed"
            for condition in CONDITIONS
        ):
            complete_pair_differences.append(
                {
                    "task_id": task_id,
                    "repeat": repeat,
                    "difference": (
                        int(pair["forced_verified_oracle_parameters"]["correct"])
                        - int(pair["no_tool"]["correct"])
                    ),
                }
            )
        else:
            incomplete_pairs.append({"task_id": task_id, "repeat": repeat})

    task_results = []
    for task_id, rows in sorted(by_task.items()):
        condition_accuracy = {}
        for condition in CONDITIONS:
            selected = [
                row
                for row in rows
                if row["condition"] == condition and row["status"] == "completed"
            ]
            condition_accuracy[condition] = (
                sum(bool(row["correct"]) for row in selected) / len(selected)
                if selected
                else None
            )
        values = list(condition_accuracy.values())
        difference = (
            condition_accuracy["forced_verified_oracle_parameters"]
            - condition_accuracy["no_tool"]
            if all(value is not None for value in values)
            else None
        )
        task_results.append(
            {
                "task_id": task_id,
                "task_family_id": rows[0]["task_family_id"],
                "source_tool_id": rows[0]["source_tool_id"],
                "condition_accuracy": condition_accuracy,
                "accuracy_difference": difference,
            }
        )

    family_results = []
    grouped_tasks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in task_results:
        grouped_tasks[task["task_family_id"]].append(task)
    for family_id, tasks in sorted(grouped_tasks.items()):
        complete = [
            task for task in tasks if task["accuracy_difference"] is not None
        ]
        family_results.append(
            {
                "task_family_id": family_id,
                "source_tool_id": tasks[0]["source_tool_id"],
                "task_count": len(tasks),
                "mean_task_accuracy_no_tool": (
                    sum(task["condition_accuracy"]["no_tool"] for task in complete)
                    / len(complete)
                    if complete
                    else None
                ),
                "mean_task_accuracy_forced": (
                    sum(
                        task["condition_accuracy"][
                            "forced_verified_oracle_parameters"
                        ]
                        for task in complete
                    )
                    / len(complete)
                    if complete
                    else None
                ),
                "mean_task_accuracy_difference": (
                    sum(task["accuracy_difference"] for task in complete)
                    / len(complete)
                    if complete
                    else None
                ),
            }
        )

    differences = [
        row["accuracy_difference"]
        for row in task_results
        if row["accuracy_difference"] is not None
    ]
    return {
        "cell_count": len(records),
        "condition_summary": condition_summary,
        "scheduled_pair_count": len(by_pair),
        "complete_pair_count": len(complete_pair_differences),
        "incomplete_pair_count": len(incomplete_pairs),
        "paired_cell_accuracy_gain": (
            sum(row["difference"] for row in complete_pair_differences)
            / len(complete_pair_differences)
            if complete_pair_differences
            else None
        ),
        "task_count": len(task_results),
        "task_level_mean_accuracy_gain": (
            sum(differences) / len(differences) if differences else None
        ),
        "positive_gain_task_count": sum(value > 0 for value in differences),
        "zero_gain_task_count": sum(value == 0 for value in differences),
        "negative_gain_task_count": sum(value < 0 for value in differences),
        "task_results": task_results,
        "family_results": family_results,
        "incomplete_pairs": incomplete_pairs,
        "analysis_status": "descriptive_development_only",
        "confirmatory_inference_allowed": False,
    }


def write_analysis(run_dir: Path, output_dir: Path) -> dict[str, Any]:
    source_manifest = verify_manifest(run_dir)
    records_path = run_dir / "run_records.jsonl"
    report_path = run_dir / "run_report.json"
    source_report = json.loads(report_path.read_text(encoding="utf-8"))
    analysis = analyze_records(load_records(records_path))

    output_dir.mkdir(parents=True, exist_ok=False)
    analysis_path = output_dir / "analysis_report.json"
    report = {
        "schema_version": "1.0",
        "analysis_id": "E1B-DEVELOPMENT-ANALYSIS-V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_run_id": source_report["run_id"],
        "source_manifest_sha256": file_hash(run_dir / "artifact_manifest.json"),
        "source_records_sha256": file_hash(records_path),
        "source_manifest_artifact_count": len(source_manifest["artifacts"]),
        **analysis,
        "limitations": [
            "任务仅14个且来自5个verified_core工具",
            "模型仅deepseek-v4-flash",
            "重复运行不视为独立任务样本",
            "未进行正式功效分析或确认性假设检验",
        ],
        "core_frozen": False,
    }
    analysis_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest_path = output_dir / "artifact_manifest.json"
    manifest = {
        "schema_version": "1.0",
        "analysis_id": report["analysis_id"],
        "artifacts": [
            {"filename": analysis_path.name, "sha256": file_hash(analysis_path)}
        ],
        "source_evidence": [
            {
                "filename": project_relative(run_dir / "artifact_manifest.json"),
                "sha256": report["source_manifest_sha256"],
            },
            {
                "filename": project_relative(records_path),
                "sha256": report["source_records_sha256"],
            },
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = write_analysis(args.run_dir, args.output_dir)
    print(
        json.dumps(
            {
                "source_run_id": report["source_run_id"],
                "cell_count": report["cell_count"],
                "task_count": report["task_count"],
                "paired_cell_accuracy_gain": report["paired_cell_accuracy_gain"],
                "analysis_status": report["analysis_status"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
