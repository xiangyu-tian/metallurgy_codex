"""Prepare the complete E1b v2 benefit-estimation task snapshot."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[2]

try:
    from .generate_e1b_v2 import file_hash, load_json, project_relative, write_json
except ImportError:  # direct script execution
    from generate_e1b_v2 import (  # type: ignore[no-redef]
        file_hash,
        load_json,
        project_relative,
        write_json,
    )


EXPECTED_COUNTS = {
    "A001": 10,
    "A002": 7,
    "A003": 12,
    "A004": 8,
    "B019": 8,
}


def prepare_benefit_subset(
    source_tasks_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    source_doc = load_json(source_tasks_path)
    tasks = [
        task
        for task in source_doc["tasks"]
        if task["split"] == "benefit_estimation"
    ]
    counts = Counter(task["source_tool_id"] for task in tasks)
    if len(tasks) != 45:
        raise ValueError(f"expected 45 benefit tasks, found {len(tasks)}")
    if counts != Counter(EXPECTED_COUNTS):
        raise ValueError(f"unexpected benefit task counts: {dict(counts)}")
    if any(task["split"] == "gate_evaluation" for task in tasks):
        raise ValueError("benefit snapshot must not include gate_evaluation")
    if len({task["task_id"] for task in tasks}) != len(tasks):
        raise ValueError("benefit snapshot contains duplicate task ids")

    output_dir.mkdir(parents=True, exist_ok=True)
    tasks_path = output_dir / "e1b_benefit_tasks_v2.json"
    benefit_doc = {
        "schema_version": "2.0",
        "dataset_id": "E1B-TASKSET-V2-BENEFIT-20260730",
        "dataset_status": "prepared_development",
        "protocol_version": source_doc["protocol_version"],
        "generator_version": source_doc["generator_version"],
        "generated_at": source_doc["generated_at"],
        "source_dataset_id": source_doc["dataset_id"],
        "source_dataset_sha256": file_hash(source_tasks_path),
        "required_split": "benefit_estimation",
        "task_count": len(tasks),
        "tasks": tasks,
        "gate_evaluation_opened": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    write_json(tasks_path, benefit_doc)

    report_path = output_dir / "preparation_report.json"
    report = {
        "schema_version": "1.0",
        "dataset_id": benefit_doc["dataset_id"],
        "status": "passed",
        "task_count": len(tasks),
        "condition_run_cells_per_repeat": len(tasks) * 2,
        "condition_run_cells_at_three_repeats": len(tasks) * 2 * 3,
        "task_count_by_tool": dict(sorted(counts.items())),
        "base_task_group_count": len(
            {task["base_task_group_id"] for task in tasks}
        ),
        "selected_splits": sorted({task["split"] for task in tasks}),
        "gate_evaluation_task_count": 0,
        "api_model_runs_performed": False,
        "core_frozen": False,
    }
    write_json(report_path, report)

    manifest_path = output_dir / "artifact_manifest.json"
    manifest = {
        "schema_version": "1.0",
        "dataset_id": benefit_doc["dataset_id"],
        "artifacts": [
            {"filename": tasks_path.name, "sha256": file_hash(tasks_path)},
            {"filename": report_path.name, "sha256": file_hash(report_path)},
            {
                "filename": project_relative(source_tasks_path),
                "sha256": file_hash(source_tasks_path),
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
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "e1b_benefit_taskset_v2_20260730",
    )
    args = parser.parse_args()
    report = prepare_benefit_subset(args.source_tasks, args.output_dir)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
