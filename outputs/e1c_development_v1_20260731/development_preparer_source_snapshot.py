"""Prepare the E1c development-only snapshot while keeping evaluation sealed."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[2]

try:
    from .generate_e1c_tasks import project_relative
    from ..e1b_v2.apply_candidate_gate_policy import (
        file_hash,
        load_json,
        write_json,
    )
except ImportError:  # direct execution
    import sys

    TOOLS_DIR = HERE.parents[1]
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))
    from core_freeze.e1c_end_to_end.generate_e1c_tasks import project_relative
    from core_freeze.e1b_v2.apply_candidate_gate_policy import (
        file_hash,
        load_json,
        write_json,
    )


def prepare_development(
    source_tasks_path: Path,
    protocol_path: Path,
    prompts_path: Path,
    config_path: Path,
    policy_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    source = load_json(source_tasks_path)
    prompts = load_json(prompts_path)
    config = load_json(config_path)
    if source.get("evaluation_split_opened") is not False:
        raise ValueError("source evaluation split must still be sealed")
    if config.get("selected_split") != "runner_development":
        raise ValueError("development config selects the wrong split")
    if config.get("evaluation_split_opened") is not False:
        raise ValueError("development config must keep evaluation sealed")
    if config.get("prompt_version") != prompts.get("prompt_version"):
        raise ValueError("prompt version mismatch")
    if config.get("protocol_sha256") != file_hash(protocol_path):
        raise ValueError("protocol hash mismatch")
    if config.get("prompt_sha256") != file_hash(prompts_path):
        raise ValueError("prompt hash mismatch")
    if file_hash(policy_path) != config.get("frozen_policy_sha256"):
        raise ValueError("development config policy hash mismatch")

    tasks = [
        task
        for task in source["tasks"]
        if task["split"] == "runner_development"
    ]
    if len(tasks) != 24:
        raise ValueError(f"expected 24 development tasks, found {len(tasks)}")
    if any(task["split"] == "end_to_end_evaluation" for task in tasks):
        raise ValueError("development snapshot contains evaluation task")

    output_dir.mkdir(parents=True, exist_ok=True)
    tasks_path = output_dir / "e1c_development_tasks_v1.json"
    doc = {
        "schema_version": "1.0",
        "dataset_id": config["dataset_id"],
        "dataset_status": "prepared_development_pre_api",
        "source_dataset_id": source["dataset_id"],
        "source_dataset_sha256": file_hash(source_tasks_path),
        "protocol_id": config["protocol_id"],
        "protocol_sha256": config["protocol_sha256"],
        "prompt_version": prompts["prompt_version"],
        "frozen_policy_id": config["frozen_policy_id"],
        "frozen_policy_sha256": config["frozen_policy_sha256"],
        "required_split": "runner_development",
        "task_count": len(tasks),
        "tasks": tasks,
        "evaluation_split_opened": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    write_json(tasks_path, doc)

    snapshots = [
        (protocol_path, output_dir / protocol_path.name),
        (prompts_path, output_dir / prompts_path.name),
        (config_path, output_dir / config_path.name),
        (policy_path, output_dir / policy_path.name),
        (
            Path(__file__),
            output_dir / "development_preparer_source_snapshot.py",
        ),
        (HERE / "run_e1c.py", output_dir / "runner_source_snapshot.py"),
        (
            HERE.parent / "e1b_pilot" / "e1b_scoring.py",
            output_dir / "scoring_source_snapshot.py",
        ),
    ]
    for source_path, target_path in snapshots:
        target_path.write_bytes(source_path.read_bytes())

    report_path = output_dir / "preparation_report.json"
    report = {
        "schema_version": "1.0",
        "dataset_id": doc["dataset_id"],
        "status": "passed",
        "task_count": len(tasks),
        "condition_count": len(config["conditions"]),
        "scheduled_cells_at_one_repeat": len(tasks) * len(config["conditions"]),
        "task_count_by_tool": dict(
            sorted(Counter(task["source_tool_id"] for task in tasks).items())
        ),
        "policy_action_task_counts": dict(
            sorted(
                Counter(
                    task["frozen_policy_decision"]["action"]
                    for task in tasks
                ).items()
            )
        ),
        "evaluation_task_count": 0,
        "evaluation_split_opened": False,
        "api_model_runs_performed": False,
        "runner_sha256": file_hash(HERE / "run_e1c.py"),
        "core_frozen": False,
    }
    write_json(report_path, report)

    manifest_path = output_dir / "artifact_manifest.json"
    artifacts = [tasks_path] + [
        target_path for _, target_path in snapshots
    ] + [report_path]
    manifest = {
        "schema_version": "1.0",
        "dataset_id": doc["dataset_id"],
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
                "filename": project_relative(protocol_path),
                "sha256": file_hash(protocol_path),
            },
            {
                "filename": project_relative(prompts_path),
                "sha256": file_hash(prompts_path),
            },
            {
                "filename": project_relative(config_path),
                "sha256": file_hash(config_path),
            },
            {
                "filename": project_relative(policy_path),
                "sha256": file_hash(policy_path),
            },
            {
                "filename": project_relative(HERE / "run_e1c.py"),
                "sha256": file_hash(HERE / "run_e1c.py"),
            },
            {
                "filename": project_relative(Path(__file__)),
                "sha256": file_hash(Path(__file__)),
            },
            {
                "filename": project_relative(
                    HERE.parent / "e1b_pilot" / "e1b_scoring.py"
                ),
                "sha256": file_hash(
                    HERE.parent / "e1b_pilot" / "e1b_scoring.py"
                ),
            },
        ],
        "evaluation_split_opened": False,
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
            / "e1c_taskset_v1_20260731"
            / "e1c_tasks_v1.json"
        ),
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=HERE / "protocol_v1.md",
    )
    parser.add_argument(
        "--prompts",
        type=Path,
        default=HERE / "prompts_v1.json",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=HERE / "run_config_development_v1.json",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=HERE.parent / "e1b_v2" / "candidate_gate_policy_v1.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "e1c_development_v1_20260731",
    )
    args = parser.parse_args()
    report = prepare_development(
        args.source_tasks,
        args.protocol,
        args.prompts,
        args.config,
        args.policy,
        args.output_dir,
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
