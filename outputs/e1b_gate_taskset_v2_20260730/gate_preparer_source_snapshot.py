"""Open the sealed E1b v2 gate split under a previously frozen policy."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[2]
FROZEN_POLICY_COMMIT = "1ee098e"
EXPECTED_COUNTS = {
    "A001": 6,
    "A002": 5,
    "A003": 8,
    "A004": 4,
    "B019": 4,
}

try:
    from .apply_candidate_gate_policy import (
        classify_task,
        file_hash,
        load_json,
        validate_policy,
        write_json,
    )
except ImportError:  # direct script execution
    from apply_candidate_gate_policy import (  # type: ignore[no-redef]
        classify_task,
        file_hash,
        load_json,
        validate_policy,
        write_json,
    )


def project_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def prepare_gate_snapshot(
    source_tasks_path: Path,
    policy_path: Path,
    run_config_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    source_doc = load_json(source_tasks_path)
    policy = load_json(policy_path)
    run_config = load_json(run_config_path)
    validate_policy(policy)
    if source_doc.get("dataset_id") != "E1B-TASKSET-V2-20260730":
        raise ValueError("unexpected source dataset")
    if file_hash(source_tasks_path) != (
        "1193b238ac20ae131f6c97398f5ae4dcdcdc6f937c57973986368f8363afdf03"
    ):
        raise ValueError("source taskset hash does not match frozen v2 taskset")
    if file_hash(policy_path) != (
        "4d34ddc0a8d53d46f0aabf1469469dab243b9ddb6c03a5e8e849b9763801c1d5"
    ):
        raise ValueError("candidate policy hash does not match frozen v1")
    if run_config.get("dataset_id") != "E1B-TASKSET-V2-GATE-20260730":
        raise ValueError("gate run config has unexpected dataset id")
    if run_config.get("selected_split") != "gate_evaluation":
        raise ValueError("gate run config must select gate_evaluation")
    if run_config.get("gate_evaluation_opened") is not True:
        raise ValueError("gate run config must explicitly open gate evaluation")
    if run_config.get("policy_revision_allowed") is not False:
        raise ValueError("gate run config must forbid policy revision")
    if run_config.get("frozen_policy_sha256") != file_hash(policy_path):
        raise ValueError("gate run config does not bind the frozen policy")

    tasks = [
        task for task in source_doc["tasks"] if task["split"] == "gate_evaluation"
    ]
    counts = Counter(task["source_tool_id"] for task in tasks)
    if len(tasks) != 27:
        raise ValueError(f"expected 27 gate tasks, found {len(tasks)}")
    if counts != Counter(EXPECTED_COUNTS):
        raise ValueError(f"unexpected gate task counts: {dict(counts)}")
    if len({task["task_id"] for task in tasks}) != len(tasks):
        raise ValueError("gate snapshot contains duplicate task ids")
    benefit_groups = {
        task["base_task_group_id"]
        for task in source_doc["tasks"]
        if task["split"] == "benefit_estimation"
    }
    gate_groups = {task["base_task_group_id"] for task in tasks}
    overlap = sorted(benefit_groups & gate_groups)
    if overlap:
        raise ValueError(f"gate groups overlap benefit groups: {overlap}")

    decisions = []
    for task in tasks:
        decision = classify_task(task, policy)
        decisions.append(
            {
                "task_id": task["task_id"],
                "source_tool_id": task["source_tool_id"],
                "base_task_group_id": task["base_task_group_id"],
                "precision_policy": task["precision_policy"],
                "composition_dynamic_range": (
                    ""
                    if decision["composition_dynamic_range"] is None
                    else f"{decision['composition_dynamic_range']:.12g}"
                ),
                "composition_requires_rescaling": (
                    ""
                    if decision["composition_requires_rescaling"] is None
                    else str(
                        decision["composition_requires_rescaling"]
                    ).lower()
                ),
                "action": decision["action"],
                "rule_id": decision["rule_id"],
                "reason_code": decision["reason_code"],
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    tasks_path = output_dir / "e1b_gate_tasks_v2.json"
    gate_doc = {
        "schema_version": "2.0",
        "dataset_id": "E1B-TASKSET-V2-GATE-20260730",
        "dataset_status": "opened_independent_gate",
        "protocol_version": source_doc["protocol_version"],
        "generator_version": source_doc["generator_version"],
        "generated_at": source_doc["generated_at"],
        "gate_opened_at": "2026-07-30T00:00:00+08:00",
        "source_dataset_id": source_doc["dataset_id"],
        "source_dataset_sha256": file_hash(source_tasks_path),
        "required_split": "gate_evaluation",
        "task_count": len(tasks),
        "tasks": tasks,
        "gate_evaluation_opened": True,
        "frozen_policy_id": policy["policy_id"],
        "frozen_policy_version": policy["policy_version"],
        "frozen_policy_sha256": file_hash(policy_path),
        "frozen_policy_git_commit": FROZEN_POLICY_COMMIT,
        "policy_revision_allowed": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    write_json(tasks_path, gate_doc)

    assignments_path = output_dir / "pre_run_policy_assignments.csv"
    with assignments_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(decisions[0]))
        writer.writeheader()
        writer.writerows(decisions)

    policy_snapshot_path = output_dir / policy_path.name
    policy_snapshot_path.write_bytes(policy_path.read_bytes())
    config_snapshot_path = output_dir / run_config_path.name
    config_snapshot_path.write_bytes(run_config_path.read_bytes())
    preparer_snapshot_path = output_dir / "gate_preparer_source_snapshot.py"
    preparer_snapshot_path.write_bytes(Path(__file__).read_bytes())

    report_path = output_dir / "gate_opening_report.json"
    report = {
        "schema_version": "1.0",
        "dataset_id": gate_doc["dataset_id"],
        "status": "passed",
        "gate_evaluation_opened": True,
        "task_count": len(tasks),
        "condition_run_cells_per_repeat": len(tasks) * 2,
        "condition_run_cells_at_three_repeats": len(tasks) * 2 * 3,
        "task_count_by_tool": dict(sorted(counts.items())),
        "base_task_group_count": len(gate_groups),
        "benefit_gate_group_overlap_count": 0,
        "policy_action_task_counts": dict(
            sorted(Counter(row["action"] for row in decisions).items())
        ),
        "policy_rule_task_counts": dict(
            sorted(Counter(row["rule_id"] for row in decisions).items())
        ),
        "frozen_policy_sha256": file_hash(policy_path),
        "frozen_policy_git_commit": FROZEN_POLICY_COMMIT,
        "run_config_sha256": file_hash(run_config_path),
        "policy_assignments_created_before_api_run": True,
        "api_model_runs_performed": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    write_json(report_path, report)

    manifest_path = output_dir / "artifact_manifest.json"
    artifacts = [
        tasks_path,
        assignments_path,
        policy_snapshot_path,
        config_snapshot_path,
        preparer_snapshot_path,
        report_path,
    ]
    manifest = {
        "schema_version": "1.0",
        "dataset_id": gate_doc["dataset_id"],
        "artifacts": [
            {"filename": path.name, "sha256": file_hash(path)}
            for path in artifacts
        ],
        "source_artifacts": [
            {
                "filename": project_relative(source_tasks_path),
                "sha256": file_hash(source_tasks_path),
            },
            {
                "filename": project_relative(policy_path),
                "sha256": file_hash(policy_path),
            },
            {
                "filename": project_relative(run_config_path),
                "sha256": file_hash(run_config_path),
            },
        ],
        "gate_evaluation_opened": True,
        "policy_revision_allowed": False,
        "core_frozen": False,
    }
    write_json(manifest_path, manifest)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-tasks",
        type=Path,
        default=(
            PROJECT_ROOT
            / "outputs"
            / "e1b_taskset_v2_20260730"
            / "e1b_tasks_v2.json"
        ),
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=HERE / "candidate_gate_policy_v1.json",
    )
    parser.add_argument(
        "--run-config",
        type=Path,
        default=HERE / "run_config_gate_v2.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "e1b_gate_taskset_v2_20260730",
    )
    args = parser.parse_args()
    report = prepare_gate_snapshot(
        args.source_tasks,
        args.policy,
        args.run_config,
        args.output_dir,
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
