"""Analyze the complete E1b v2 benefit-estimation development run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
E1B_PILOT_DIR = HERE.parent / "e1b_pilot"
PROJECT_ROOT = HERE.parents[2]
if str(E1B_PILOT_DIR) not in sys.path:
    sys.path.insert(0, str(E1B_PILOT_DIR))

from analyze_e1b_pilot import load_records, verify_manifest  # noqa: E402


CONDITIONS = ("no_tool", "forced_verified_oracle_parameters")
BOOTSTRAP_SEED = 20260730
BOOTSTRAP_ITERATIONS = 10_000


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_relative(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT).as_posix()


def write_json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def percentile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("percentile requires at least one value")
    position = (len(sorted_values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return (
        sorted_values[lower] * (1.0 - weight)
        + sorted_values[upper] * weight
    )


def cluster_bootstrap(
    group_differences: dict[str, list[float]],
    *,
    seed: int = BOOTSTRAP_SEED,
    iterations: int = BOOTSTRAP_ITERATIONS,
) -> dict[str, Any]:
    if not group_differences:
        raise ValueError("cluster bootstrap requires groups")
    if iterations < 1:
        raise ValueError("bootstrap iterations must be positive")
    group_ids = sorted(group_differences)
    if any(not values for values in group_differences.values()):
        raise ValueError("every bootstrap group must contain paired differences")
    rng = random.Random(seed)
    task_weighted = []
    group_equal = []
    for _ in range(iterations):
        sampled = [rng.choice(group_ids) for _ in group_ids]
        selected_values = [
            difference
            for group_id in sampled
            for difference in group_differences[group_id]
        ]
        selected_group_means = [
            sum(group_differences[group_id]) / len(group_differences[group_id])
            for group_id in sampled
        ]
        task_weighted.append(sum(selected_values) / len(selected_values))
        group_equal.append(
            sum(selected_group_means) / len(selected_group_means)
        )
    task_weighted.sort()
    group_equal.sort()
    observed_values = [
        value for values in group_differences.values() for value in values
    ]
    observed_group_means = [
        sum(values) / len(values) for values in group_differences.values()
    ]
    return {
        "seed": seed,
        "iterations": iterations,
        "cluster_unit": "base_task_group_id",
        "task_weighted": {
            "estimate": sum(observed_values) / len(observed_values),
            "ci95": [
                percentile(task_weighted, 0.025),
                percentile(task_weighted, 0.975),
            ],
        },
        "group_equal": {
            "estimate": (
                sum(observed_group_means) / len(observed_group_means)
            ),
            "ci95": [
                percentile(group_equal, 0.025),
                percentile(group_equal, 0.975),
            ],
        },
        "confirmatory_inference_allowed": False,
    }


def paired_rows(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    units: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in records:
        key = (row["task_id"], int(row["model_run_repeat"]))
        condition = row["condition"]
        if condition in units[key]:
            raise ValueError(f"duplicate paired cell: {key} {condition}")
        units[key][condition] = row
    pairs = []
    for (task_id, repeat), conditions in sorted(units.items()):
        if set(conditions) != set(CONDITIONS):
            raise ValueError(f"incomplete paired unit: {task_id} repeat {repeat}")
        if any(conditions[name]["status"] != "completed" for name in CONDITIONS):
            raise ValueError(f"non-completed paired unit: {task_id} repeat {repeat}")
        no_tool = conditions["no_tool"]
        forced = conditions["forced_verified_oracle_parameters"]
        pairs.append(
            {
                "task_id": task_id,
                "repeat": repeat,
                "source_tool_id": no_tool["source_tool_id"],
                "base_task_group_id": no_tool["base_task_group_id"],
                "precision_policy": no_tool["precision_policy"],
                "no_tool_correct": int(no_tool["correct"]),
                "forced_correct": int(forced["correct"]),
                "difference": int(forced["correct"]) - int(no_tool["correct"]),
            }
        )
    return pairs


def aggregate_effects(
    pairs: list[dict[str, Any]],
    key: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pairs:
        grouped[str(row[key])].append(row)
    results = []
    for value, rows in sorted(grouped.items()):
        results.append(
            {
                key: value,
                "paired_cell_count": len(rows),
                "no_tool_accuracy": (
                    sum(row["no_tool_correct"] for row in rows) / len(rows)
                ),
                "forced_accuracy": (
                    sum(row["forced_correct"] for row in rows) / len(rows)
                ),
                "accuracy_gain": (
                    sum(row["difference"] for row in rows) / len(rows)
                ),
            }
        )
    return results


def condition_cost_summary(
    records: list[dict[str, Any]],
    condition: str,
) -> dict[str, Any]:
    rows = [row for row in records if row["condition"] == condition]
    usage_totals: dict[str, int] = defaultdict(int)
    for row in rows:
        usage = row.get("response_metadata", {}).get("usage") or {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                usage_totals[key] += value
    return {
        "cell_count": len(rows),
        "usage_totals": dict(usage_totals),
        "mean_latency_ms": (
            sum(float(row["latency_ms"]) for row in rows) / len(rows)
            if rows
            else None
        ),
    }


def build_analysis(
    records: list[dict[str, Any]],
    tasks_doc: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if tasks_doc["task_count"] != 45:
        raise ValueError("benefit analysis requires exactly 45 tasks")
    if any(task["split"] != "benefit_estimation" for task in tasks_doc["tasks"]):
        raise ValueError("benefit analysis received a non-benefit task")
    if len(records) != 270:
        raise ValueError(f"benefit analysis requires 270 cells, found {len(records)}")
    if {int(row["model_run_repeat"]) for row in records} != {1, 2, 3}:
        raise ValueError("benefit analysis requires repeats 1, 2, and 3")
    if any(row.get("split") != "benefit_estimation" for row in records):
        raise ValueError("run records contain a non-benefit split")

    pairs = paired_rows(records)
    if len(pairs) != 135:
        raise ValueError(f"expected 135 complete pairs, found {len(pairs)}")
    task_metadata = {task["task_id"]: task for task in tasks_doc["tasks"]}
    if {row["task_id"] for row in pairs} != set(task_metadata):
        raise ValueError("run task ids differ from the frozen task snapshot")

    task_effects = []
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    group_differences: dict[str, list[float]] = defaultdict(list)
    for row in pairs:
        by_task[row["task_id"]].append(row)
        group_differences[row["base_task_group_id"]].append(
            float(row["difference"])
        )
    for task_id, rows in sorted(by_task.items()):
        task = task_metadata[task_id]
        no_tool_correct = sum(row["no_tool_correct"] for row in rows)
        forced_correct = sum(row["forced_correct"] for row in rows)
        task_effects.append(
            {
                "task_id": task_id,
                "source_tool_id": task["source_tool_id"],
                "base_task_group_id": task["base_task_group_id"],
                "precision_policy": task["precision_policy"],
                "no_tool_correct_repeats": no_tool_correct,
                "forced_correct_repeats": forced_correct,
                "repeat_count": len(rows),
                "accuracy_gain": (
                    (forced_correct - no_tool_correct) / len(rows)
                ),
            }
        )

    group_effects = []
    group_tasks: dict[str, set[str]] = defaultdict(set)
    for task in task_effects:
        group_tasks[task["base_task_group_id"]].add(task["task_id"])
    for group_id, differences in sorted(group_differences.items()):
        group_effects.append(
            {
                "base_task_group_id": group_id,
                "task_count": len(group_tasks[group_id]),
                "paired_cell_count": len(differences),
                "accuracy_gain": sum(differences) / len(differences),
            }
        )

    errors = []
    for row in records:
        if row["status"] == "completed" and not row["correct"]:
            errors.append(
                {
                    "task_id": row["task_id"],
                    "source_tool_id": row["source_tool_id"],
                    "base_task_group_id": row["base_task_group_id"],
                    "precision_policy": row["precision_policy"],
                    "condition": row["condition"],
                    "model_run_repeat": row["model_run_repeat"],
                    "error_mechanism": (
                        "parse_failure"
                        if row["parse_status"] != "parsed"
                        else "numeric_or_structured_mismatch"
                    ),
                    "parse_status": row["parse_status"],
                    "raw_answer": row["raw_answer"],
                }
            )

    a003_by_group: dict[str, dict[str, float]] = defaultdict(dict)
    for task in task_effects:
        if task["source_tool_id"] == "A003":
            a003_by_group[task["base_task_group_id"]][
                task["precision_policy"]
            ] = task["accuracy_gain"]
    a003_precision_pairs = []
    for group_id, policies in sorted(a003_by_group.items()):
        if set(policies) != {
            "strict_versioned",
            "approximate_educational",
        }:
            raise ValueError(f"incomplete A003 precision pair: {group_id}")
        a003_precision_pairs.append(
            {
                "base_task_group_id": group_id,
                "strict_gain": policies["strict_versioned"],
                "approximate_gain": policies["approximate_educational"],
                "strict_minus_approximate_gain": (
                    policies["strict_versioned"]
                    - policies["approximate_educational"]
                ),
            }
        )

    tool_effects = aggregate_effects(pairs, "source_tool_id")
    precision_effects = aggregate_effects(pairs, "precision_policy")
    bootstrap = cluster_bootstrap(group_differences)
    differences = [float(row["difference"]) for row in pairs]
    no_tool_rows = [row for row in records if row["condition"] == "no_tool"]
    forced_rows = [
        row
        for row in records
        if row["condition"] == "forced_verified_oracle_parameters"
    ]

    report = {
        "cell_count": len(records),
        "task_count": len(task_effects),
        "base_task_group_count": len(group_effects),
        "paired_cell_count": len(pairs),
        "no_tool_accuracy": (
            sum(row["no_tool_correct"] for row in pairs) / len(pairs)
        ),
        "forced_accuracy": (
            sum(row["forced_correct"] for row in pairs) / len(pairs)
        ),
        "paired_accuracy_gain": sum(differences) / len(differences),
        "positive_pair_count": sum(value > 0 for value in differences),
        "zero_pair_count": sum(value == 0 for value in differences),
        "negative_pair_count": sum(value < 0 for value in differences),
        "no_tool_parse_failure_count": sum(
            row["parse_status"] != "parsed" for row in no_tool_rows
        ),
        "forced_parse_failure_count": sum(
            row["parse_status"] != "parsed" for row in forced_rows
        ),
        "provider_attempt_count": sum(
            int(row.get("provider_attempt_count", 0)) for row in records
        ),
        "retried_cell_count": sum(
            int(row.get("provider_attempt_count", 0)) > 1 for row in records
        ),
        "condition_costs": {
            condition: condition_cost_summary(records, condition)
            for condition in CONDITIONS
        },
        "tool_effects": tool_effects,
        "precision_policy_effects": precision_effects,
        "a003_precision_pairs": a003_precision_pairs,
        "a003_mean_strict_minus_approximate_gain": (
            sum(
                row["strict_minus_approximate_gain"]
                for row in a003_precision_pairs
            )
            / len(a003_precision_pairs)
        ),
        "cluster_bootstrap": bootstrap,
        "no_observed_benefit_scopes": [
            row["source_tool_id"]
            for row in tool_effects
            if row["accuracy_gain"] == 0
        ],
        "high_observed_benefit_policies": [
            row["precision_policy"]
            for row in precision_effects
            if row["accuracy_gain"] >= 0.5
        ],
        "intermittent_observed_benefit_policies": [
            row["precision_policy"]
            for row in precision_effects
            if 0 < row["accuracy_gain"] < 0.5
        ],
        "analysis_status": "descriptive_development_only",
        "gate_evaluation_opened": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    return report, task_effects, group_effects, errors


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty CSV: {path.name}")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_benefit_analysis(run_dir: Path, output_dir: Path) -> dict[str, Any]:
    source_manifest = verify_manifest(run_dir)
    source_report_path = run_dir / "run_report.json"
    source_records_path = run_dir / "run_records.jsonl"
    source_tasks_path = run_dir / "task_source_snapshot.json"
    source_report = json.loads(source_report_path.read_text(encoding="utf-8"))
    tasks_doc = json.loads(source_tasks_path.read_text(encoding="utf-8"))
    records = load_records(source_records_path)
    analysis, task_effects, group_effects, errors = build_analysis(
        records,
        tasks_doc,
    )

    output_dir.mkdir(parents=True, exist_ok=False)
    analyzer_snapshot_path = output_dir / "analyzer_source_snapshot.py"
    shutil.copyfile(Path(__file__), analyzer_snapshot_path)
    task_effects_path = output_dir / "task_effects.csv"
    group_effects_path = output_dir / "group_effects.csv"
    error_audit_path = output_dir / "error_audit.csv"
    write_csv(task_effects_path, task_effects)
    write_csv(group_effects_path, group_effects)
    write_csv(error_audit_path, errors)

    report_path = output_dir / "benefit_analysis_report.json"
    report = {
        "schema_version": "1.0",
        "analysis_id": "E1B-V2-BENEFIT-DEVELOPMENT-ANALYSIS-R3-20260730",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_run_id": source_report["run_id"],
        "source_dataset_id": source_report["dataset_id"],
        "source_run_config_id": source_report["run_config_id"],
        "source_manifest_sha256": file_hash(run_dir / "artifact_manifest.json"),
        "source_records_sha256": file_hash(source_records_path),
        "source_manifest_artifact_count": len(source_manifest["artifacts"]),
        "analyzer_source_sha256": file_hash(analyzer_snapshot_path),
        **analysis,
    }
    write_json(report_path, report)

    manifest_path = output_dir / "artifact_manifest.json"
    manifest = {
        "schema_version": "1.0",
        "analysis_id": report["analysis_id"],
        "artifacts": [
            {"filename": report_path.name, "sha256": file_hash(report_path)},
            {
                "filename": task_effects_path.name,
                "sha256": file_hash(task_effects_path),
            },
            {
                "filename": group_effects_path.name,
                "sha256": file_hash(group_effects_path),
            },
            {
                "filename": error_audit_path.name,
                "sha256": file_hash(error_audit_path),
            },
            {
                "filename": analyzer_snapshot_path.name,
                "sha256": file_hash(analyzer_snapshot_path),
            },
        ],
        "source_evidence": [
            {
                "filename": project_relative(run_dir / "artifact_manifest.json"),
                "sha256": report["source_manifest_sha256"],
            },
            {
                "filename": project_relative(source_records_path),
                "sha256": report["source_records_sha256"],
            },
        ],
    }
    write_json(manifest_path, manifest)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = write_benefit_analysis(args.run_dir, args.output_dir)
    print(
        json.dumps(
            {
                "source_run_id": report["source_run_id"],
                "paired_cell_count": report["paired_cell_count"],
                "paired_accuracy_gain": report["paired_accuracy_gain"],
                "cluster_bootstrap": report["cluster_bootstrap"],
                "analysis_status": report["analysis_status"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
