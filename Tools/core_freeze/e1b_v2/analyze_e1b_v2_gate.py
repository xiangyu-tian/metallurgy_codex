"""Evaluate frozen candidate gate policy v1 on the independent E1b gate run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[2]
POLICY_SHA256 = (
    "4d34ddc0a8d53d46f0aabf1469469dab243b9ddb6c03a5e8e849b9763801c1d5"
)
CONDITIONS = {"no_tool", "forced_verified_oracle_parameters"}


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_manifest(directory: Path) -> dict[str, Any]:
    manifest = load_json(directory / "artifact_manifest.json")
    names: set[str] = set()
    for row in manifest["artifacts"]:
        name = row["filename"]
        if name in names:
            raise ValueError(f"duplicate manifest artifact: {name}")
        names.add(name)
        path = directory / name
        if not path.is_file():
            raise ValueError(f"missing manifest artifact: {name}")
        if file_hash(path) != row["sha256"]:
            raise ValueError(f"manifest hash mismatch: {name}")
    return manifest


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid JSONL at line {line_number}: {exc}"
                ) from exc
    return records


def load_assignments(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assignments: dict[str, dict[str, str]] = {}
    for row in rows:
        task_id = row["task_id"]
        if task_id in assignments:
            raise ValueError(f"duplicate policy assignment: {task_id}")
        assignments[task_id] = row
    return assignments


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def analyze_gate(
    run_dir: Path,
    gate_snapshot_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    run_manifest = verify_manifest(run_dir)
    gate_manifest = verify_manifest(gate_snapshot_dir)
    run_report = load_json(run_dir / "run_report.json")
    tasks_doc = load_json(run_dir / "task_source_snapshot.json")
    run_config = load_json(run_dir / "run_config_snapshot.json")
    records = load_jsonl(run_dir / "run_records.jsonl")
    assignments = load_assignments(
        gate_snapshot_dir / "pre_run_policy_assignments.csv"
    )

    if run_report.get("dataset_id") != "E1B-TASKSET-V2-GATE-20260730":
        raise ValueError("unexpected gate run dataset")
    if run_report.get("summary", {}).get("status") != "completed":
        raise ValueError("gate run is not completed")
    if tasks_doc.get("gate_evaluation_opened") is not True:
        raise ValueError("gate task snapshot is not opened")
    if tasks_doc.get("frozen_policy_sha256") != POLICY_SHA256:
        raise ValueError("gate task snapshot policy hash mismatch")
    if run_config.get("frozen_policy_sha256") != POLICY_SHA256:
        raise ValueError("gate run config policy hash mismatch")
    if run_config.get("policy_revision_allowed") is not False:
        raise ValueError("gate run config permits policy revision")
    if file_hash(
        gate_snapshot_dir / "candidate_gate_policy_v1.json"
    ) != POLICY_SHA256:
        raise ValueError("gate policy snapshot hash mismatch")
    if len(tasks_doc["tasks"]) != 27 or len(assignments) != 27:
        raise ValueError("gate tasks and assignments must both contain 27 rows")
    if len(records) != 162:
        raise ValueError(f"expected 162 gate records, found {len(records)}")
    if {record.get("split") for record in records} != {"gate_evaluation"}:
        raise ValueError("records contain a non-gate split")
    if any(record.get("status") != "completed" for record in records):
        raise ValueError("all gate records must be completed")

    tasks = {task["task_id"]: task for task in tasks_doc["tasks"]}
    if set(tasks) != set(assignments):
        raise ValueError("gate task and assignment id sets differ")

    cells: dict[tuple[str, str, int], dict[str, Any]] = {}
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for record in records:
        task_id = record["task_id"]
        condition = record["condition"]
        repeat = int(record["model_run_repeat"])
        key = (task_id, condition, repeat)
        if key in cells:
            raise ValueError(f"duplicate gate cell: {key}")
        if task_id not in tasks or condition not in CONDITIONS:
            raise ValueError(f"unexpected gate cell: {key}")
        cells[key] = record
        grouped[task_id][condition].append(record)

    task_effects: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []
    for task_id in sorted(tasks):
        condition_rows = grouped[task_id]
        if set(condition_rows) != CONDITIONS:
            raise ValueError(f"incomplete condition pair for {task_id}")
        for condition in CONDITIONS:
            repeats = sorted(
                int(row["model_run_repeat"])
                for row in condition_rows[condition]
            )
            if repeats != [1, 2, 3]:
                raise ValueError(
                    f"incomplete repeats for {task_id}/{condition}: {repeats}"
                )
        no_rows = condition_rows["no_tool"]
        forced_rows = condition_rows["forced_verified_oracle_parameters"]
        no_correct = sum(row["correct"] is True for row in no_rows)
        forced_correct = sum(row["correct"] is True for row in forced_rows)
        assignment = assignments[task_id]
        selected_correct = (
            forced_correct
            if assignment["action"] == "CALL_VERIFIED_TOOL"
            else no_correct
        )
        task = tasks[task_id]
        task_effects.append(
            {
                "task_id": task_id,
                "source_tool_id": task["source_tool_id"],
                "base_task_group_id": task["base_task_group_id"],
                "precision_policy": task["precision_policy"],
                "action": assignment["action"],
                "rule_id": assignment["rule_id"],
                "no_tool_correct_repeats": no_correct,
                "forced_correct_repeats": forced_correct,
                "selected_correct_repeats": selected_correct,
                "repeat_count": 3,
                "observed_gain_repeats": forced_correct - no_correct,
            }
        )
        for row in no_rows + forced_rows:
            if row["correct"] is True:
                continue
            first_check = (row.get("check_results") or [{}])[0]
            error_rows.append(
                {
                    "task_id": task_id,
                    "source_tool_id": task["source_tool_id"],
                    "base_task_group_id": task["base_task_group_id"],
                    "precision_policy": task["precision_policy"],
                    "action": assignment["action"],
                    "rule_id": assignment["rule_id"],
                    "condition": row["condition"],
                    "model_run_repeat": row["model_run_repeat"],
                    "parse_status": row.get("parse_status"),
                    "raw_answer": row.get("raw_answer"),
                    "expected": first_check.get("expected"),
                    "actual": first_check.get("actual"),
                    "error_type": row.get("error_type"),
                }
            )

    task_effects_path = output_dir / "gate_task_effects.csv"
    error_path = output_dir / "gate_error_audit.csv"
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        task_effects_path,
        task_effects,
        list(task_effects[0]),
    )
    write_csv(
        error_path,
        error_rows,
        [
            "task_id",
            "source_tool_id",
            "base_task_group_id",
            "precision_policy",
            "action",
            "rule_id",
            "condition",
            "model_run_repeat",
            "parse_status",
            "raw_answer",
            "expected",
            "actual",
            "error_type",
        ],
    )

    rule_rows: list[dict[str, Any]] = []
    all_rule_ids = [
        "CGP-V1-STRICT-VERSIONED",
        "CGP-V1-CONDITIONED-NORMALIZATION",
        "DEFAULT",
    ]
    for rule_id in all_rule_ids:
        rows = [row for row in task_effects if row["rule_id"] == rule_id]
        repeat_cells = sum(row["repeat_count"] for row in rows)
        no_correct = sum(row["no_tool_correct_repeats"] for row in rows)
        forced_correct = sum(row["forced_correct_repeats"] for row in rows)
        selected_correct = sum(row["selected_correct_repeats"] for row in rows)
        positive_gain = sum(
            max(0, row["observed_gain_repeats"]) for row in rows
        )
        if not rows:
            transfer_status = "not_evaluated_no_matching_gate_tasks"
        elif rule_id == "DEFAULT" and positive_gain == 0:
            transfer_status = "no_missed_benefit_observed"
        elif rule_id != "DEFAULT" and positive_gain > 0:
            transfer_status = "positive_transfer_observed"
        else:
            transfer_status = "no_positive_transfer_observed"
        rule_rows.append(
            {
                "rule_id": rule_id,
                "task_count": len(rows),
                "repeat_cell_count": repeat_cells,
                "no_tool_correct_count": no_correct,
                "forced_correct_count": forced_correct,
                "selected_correct_count": selected_correct,
                "positive_gain_cell_count": positive_gain,
                "transfer_status": transfer_status,
            }
        )
    rule_path = output_dir / "gate_rule_summary.csv"
    write_csv(rule_path, rule_rows, list(rule_rows[0]))

    total_cells = sum(row["repeat_count"] for row in task_effects)
    no_correct = sum(row["no_tool_correct_repeats"] for row in task_effects)
    forced_correct = sum(
        row["forced_correct_repeats"] for row in task_effects
    )
    selected_correct = sum(
        row["selected_correct_repeats"] for row in task_effects
    )
    call_cells = sum(
        row["repeat_count"]
        for row in task_effects
        if row["action"] == "CALL_VERIFIED_TOOL"
    )
    positive_gain = sum(
        max(0, row["observed_gain_repeats"]) for row in task_effects
    )
    captured_gain = sum(
        max(0, row["observed_gain_repeats"])
        for row in task_effects
        if row["action"] == "CALL_VERIFIED_TOOL"
    )

    condition_costs = {}
    for condition in sorted(CONDITIONS):
        rows = [row for row in records if row["condition"] == condition]
        usage = Counter()
        for row in rows:
            for key, value in (row.get("response_metadata", {}).get(
                "usage", {}
            ) or {}).items():
                if isinstance(value, (int, float)):
                    usage[key] += value
        condition_costs[condition] = {
            "cell_count": len(rows),
            "usage_totals": dict(usage),
            "mean_latency_ms": sum(row["latency_ms"] for row in rows)
            / len(rows),
        }

    report = {
        "schema_version": "1.0",
        "analysis_id": "E1B-V2-GATE-POLICY-V1-ANALYSIS-R3-20260730",
        "analysis_status": "independent_gate_evaluation_completed",
        "source_run_id": run_report["run_id"],
        "source_dataset_id": run_report["dataset_id"],
        "source_run_manifest_sha256": file_hash(
            run_dir / "artifact_manifest.json"
        ),
        "source_gate_manifest_sha256": file_hash(
            gate_snapshot_dir / "artifact_manifest.json"
        ),
        "frozen_policy_sha256": POLICY_SHA256,
        "frozen_policy_git_commit": tasks_doc["frozen_policy_git_commit"],
        "task_count": len(task_effects),
        "base_task_group_count": len(
            {row["base_task_group_id"] for row in task_effects}
        ),
        "paired_repeat_cell_count": total_cells,
        "provider_attempt_count": sum(
            int(row["provider_attempt_count"]) for row in records
        ),
        "retried_cell_count": sum(
            int(row["provider_attempt_count"]) > 1 for row in records
        ),
        "no_tool_accuracy": no_correct / total_cells,
        "forced_accuracy": forced_correct / total_cells,
        "candidate_policy_accuracy": selected_correct / total_cells,
        "candidate_policy_call_rate": call_cells / total_cells,
        "candidate_policy_call_cell_count": call_cells,
        "avoided_call_count_vs_always_forced": total_cells - call_cells,
        "candidate_gain_vs_always_no_tool": (
            selected_correct - no_correct
        )
        / total_cells,
        "candidate_loss_vs_always_forced": (
            selected_correct - forced_correct
        )
        / total_cells,
        "positive_gain_cell_count": positive_gain,
        "captured_positive_gain_cell_count": captured_gain,
        "captured_positive_gain_fraction": (
            captured_gain / positive_gain if positive_gain else None
        ),
        "action_task_counts": dict(
            sorted(Counter(row["action"] for row in task_effects).items())
        ),
        "rule_task_counts": dict(
            sorted(Counter(row["rule_id"] for row in task_effects).items())
        ),
        "rule_transfer_status": {
            row["rule_id"]: row["transfer_status"] for row in rule_rows
        },
        "condition_costs": condition_costs,
        "error_cell_count": len(error_rows),
        "interpretation": {
            "evaluation_type": "independent_held_out_gate",
            "policy_revision_during_evaluation": False,
            "strict_versioned_rule_transfer_observed": (
                next(
                    row
                    for row in rule_rows
                    if row["rule_id"] == "CGP-V1-STRICT-VERSIONED"
                )["transfer_status"]
                == "positive_transfer_observed"
            ),
            "conditioned_normalization_rule_evaluated": False,
            "confirmatory_inference_allowed": False,
            "core_freeze_status_changed": False,
        },
        "core_frozen": False,
    }
    report_path = output_dir / "gate_policy_report.json"
    write_json(report_path, report)

    analyzer_snapshot = output_dir / "analyzer_source_snapshot.py"
    analyzer_snapshot.write_bytes(Path(__file__).read_bytes())
    manifest_path = output_dir / "artifact_manifest.json"
    outputs = [
        task_effects_path,
        error_path,
        rule_path,
        report_path,
        analyzer_snapshot,
    ]
    manifest = {
        "schema_version": "1.0",
        "analysis_id": report["analysis_id"],
        "artifacts": [
            {"filename": path.name, "sha256": file_hash(path)}
            for path in outputs
        ],
        "source_artifacts": {
            "run_manifest": file_hash(run_dir / "artifact_manifest.json"),
            "run_records": file_hash(run_dir / "run_records.jsonl"),
            "gate_manifest": file_hash(
                gate_snapshot_dir / "artifact_manifest.json"
            ),
            "pre_run_policy_assignments": file_hash(
                gate_snapshot_dir / "pre_run_policy_assignments.csv"
            ),
            "frozen_policy": POLICY_SHA256,
        },
        "source_run_manifest_artifact_count": len(
            run_manifest["artifacts"]
        ),
        "source_gate_manifest_artifact_count": len(
            gate_manifest["artifacts"]
        ),
        "policy_revision_during_evaluation": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    write_json(manifest_path, manifest)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "run_dir",
        type=Path,
        nargs="?",
        default=PROJECT_ROOT / "outputs" / "e1b_v2_gate_r3_20260730",
    )
    parser.add_argument(
        "--gate-snapshot-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "e1b_gate_taskset_v2_20260730",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=(
            PROJECT_ROOT
            / "outputs"
            / "e1b_v2_gate_analysis_r3_20260730"
        ),
    )
    args = parser.parse_args()
    report = analyze_gate(
        args.run_dir,
        args.gate_snapshot_dir,
        args.output_dir,
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
