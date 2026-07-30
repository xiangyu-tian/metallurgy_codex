"""Prepare a frozen E1b v2 smoke subset without gate-evaluation tasks."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[2]

try:
    from .generate_e1b_v2 import (
        file_hash,
        load_json,
        project_relative,
        write_json,
    )
except ImportError:  # direct script execution
    from generate_e1b_v2 import (  # type: ignore[no-redef]
        file_hash,
        load_json,
        project_relative,
        write_json,
    )


def prepare_smoke_subset(
    source_tasks_path: Path,
    selection_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    source_doc = load_json(source_tasks_path)
    selection = load_json(selection_path)
    if source_doc["dataset_id"] != selection["source_dataset_id"]:
        raise ValueError("selection source_dataset_id does not match source tasks")
    requested = selection["task_ids"]
    if len(requested) != len(set(requested)):
        raise ValueError("smoke selection contains duplicate task ids")

    by_id = {task["task_id"]: task for task in source_doc["tasks"]}
    missing = [task_id for task_id in requested if task_id not in by_id]
    if missing:
        raise ValueError(f"smoke selection contains unknown task ids: {missing}")
    tasks = [by_id[task_id] for task_id in requested]
    required_split = selection["required_split"]
    wrong_split = [
        task["task_id"] for task in tasks if task["split"] != required_split
    ]
    if wrong_split:
        raise ValueError(
            f"smoke selection contains tasks outside {required_split}: {wrong_split}"
        )
    if any(task["split"] == "gate_evaluation" for task in tasks):
        raise ValueError("smoke selection must not include gate_evaluation tasks")
    if set(task["source_tool_id"] for task in tasks) != {
        "A001",
        "A002",
        "A003",
        "A004",
        "B019",
    }:
        raise ValueError("smoke selection must cover all five verified tools")

    a003 = [
        task for task in tasks if task["source_tool_id"] == "A003"
    ]
    if len(a003) != 2:
        raise ValueError("smoke selection must contain one A003 precision pair")
    if len({task["base_task_group_id"] for task in a003}) != 1:
        raise ValueError("A003 smoke precision variants must share one base group")
    if {task["precision_policy"] for task in a003} != {
        "strict_versioned",
        "approximate_educational",
    }:
        raise ValueError("A003 smoke precision pair is incomplete")

    output_dir.mkdir(parents=True, exist_ok=True)
    tasks_path = output_dir / "e1b_smoke_tasks_v2.json"
    smoke_doc = {
        "schema_version": "2.0",
        "dataset_id": "E1B-TASKSET-V2-SMOKE-20260730",
        "dataset_status": "prepared_smoke",
        "protocol_version": source_doc["protocol_version"],
        "generator_version": source_doc["generator_version"],
        "generated_at": source_doc["generated_at"],
        "source_dataset_id": source_doc["dataset_id"],
        "source_dataset_sha256": file_hash(source_tasks_path),
        "selection_id": selection["selection_id"],
        "required_split": required_split,
        "task_count": len(tasks),
        "tasks": tasks,
        "gate_evaluation_opened": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    write_json(tasks_path, smoke_doc)

    report_path = output_dir / "preparation_report.json"
    report = {
        "schema_version": "1.0",
        "dataset_id": smoke_doc["dataset_id"],
        "status": "passed",
        "task_count": len(tasks),
        "condition_run_cells_at_one_repeat": len(tasks) * 2,
        "task_count_by_tool": dict(
            sorted(Counter(task["source_tool_id"] for task in tasks).items())
        ),
        "precision_policy_counts": dict(
            sorted(Counter(task["precision_policy"] for task in tasks).items())
        ),
        "selected_splits": sorted({task["split"] for task in tasks}),
        "gate_evaluation_task_count": sum(
            task["split"] == "gate_evaluation" for task in tasks
        ),
        "api_model_runs_performed": False,
        "core_frozen": False,
    }
    write_json(report_path, report)

    manifest_path = output_dir / "artifact_manifest.json"
    manifest = {
        "schema_version": "1.0",
        "dataset_id": smoke_doc["dataset_id"],
        "artifacts": [
            {"filename": tasks_path.name, "sha256": file_hash(tasks_path)},
            {"filename": report_path.name, "sha256": file_hash(report_path)},
            {
                "filename": project_relative(source_tasks_path),
                "sha256": file_hash(source_tasks_path),
            },
            {
                "filename": project_relative(selection_path),
                "sha256": file_hash(selection_path),
            },
        ],
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
        "--selection",
        type=Path,
        default=HERE / "smoke_selection_v2.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "e1b_smoke_taskset_v2_20260730",
    )
    args = parser.parse_args()
    report = prepare_smoke_subset(
        args.source_tasks,
        args.selection,
        args.output_dir,
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
