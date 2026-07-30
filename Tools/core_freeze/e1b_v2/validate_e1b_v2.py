"""Validate E1b v2 against contracts, split rules, and production tools."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parents[1]
PROJECT_ROOT = HERE.parents[2]
VERIFIED_DIR = HERE.parent / "verified_core"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from core_freeze.e1b_pilot.e1b_scoring import score_answer  # noqa: E402
from core_freeze.e1b_v2.generate_e1b_v2 import (  # noqa: E402
    file_hash,
    load_json,
    project_relative,
    structural_errors,
    write_json,
)
from models_core.registry import ModelRegistry  # noqa: E402


def manifest_artifacts(
    *,
    tasks_path: Path,
    generation_report_path: Path,
    validation_report_path: Path,
    seeds_path: Path,
    contracts_path: Path,
) -> list[dict[str, str]]:
    return [
        {"filename": tasks_path.name, "sha256": file_hash(tasks_path)},
        {
            "filename": generation_report_path.name,
            "sha256": file_hash(generation_report_path),
        },
        {
            "filename": validation_report_path.name,
            "sha256": file_hash(validation_report_path),
        },
        {
            "filename": project_relative(seeds_path),
            "sha256": file_hash(seeds_path),
        },
        {
            "filename": project_relative(contracts_path),
            "sha256": file_hash(contracts_path),
        },
    ]


def validate_production(
    tasks: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    registry = ModelRegistry()
    discovered = registry.discover()
    errors = []
    rows = []
    for task in tasks:
        tool_id = task["source_tool_id"]
        params = task["expected_parameters"]
        validation = registry.validate(tool_id, params)
        result = registry.invoke(tool_id, params)
        score = (
            score_answer(result.result, task["scoring_rule"])
            if result.success
            else {
                "correct": False,
                "normalized_error": None,
                "check_results": [],
            }
        )
        row = {
            "task_id": task["task_id"],
            "base_task_group_id": task["base_task_group_id"],
            "split": task["split"],
            "tool_id": tool_id,
            "input_validation_passed": validation["valid"],
            "production_execution_success": result.success,
            "production_output_matches_reference": score["correct"],
            "error_code": result.error_code,
            "error": result.error,
        }
        rows.append(row)
        if not validation["valid"]:
            errors.append(
                f"{task['task_id']}: production input rejected: "
                f"{validation['errors']}"
            )
        if not result.success:
            errors.append(
                f"{task['task_id']}: production execution failed: "
                f"{result.error_code}: {result.error}"
            )
        elif not score["correct"]:
            errors.append(
                f"{task['task_id']}: production output differs from "
                "independent reference"
            )
    if discovered < 5:
        errors.append(f"production registry discovered only {discovered} tools")
    return errors, rows


def validate_package(
    tasks_path: Path,
    seeds_path: Path,
    contracts_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    tasks_doc = load_json(tasks_path)
    seeds_doc = load_json(seeds_path)
    contracts_doc = load_json(contracts_path)
    tasks = tasks_doc["tasks"]

    errors = structural_errors(tasks, contracts_doc)
    if tasks_doc.get("task_count") != len(tasks):
        errors.append("document task_count does not match tasks")
    if tasks_doc.get("dataset_status") != "prepared":
        errors.append("dataset_status must be prepared")
    if tasks_doc.get("core_frozen") is not False:
        errors.append("task package must not claim core_frozen")
    if tasks_doc.get("generator_version") != seeds_doc.get("generator_version"):
        errors.append("generator version differs from seed file")

    problem_texts = [task["problem_text"] for task in tasks]
    if len(problem_texts) != len(set(problem_texts)):
        errors.append("duplicate problem_text")

    production_errors, production_rows = validate_production(tasks)
    errors.extend(production_errors)
    status = "passed" if not errors else "failed"

    output_dir.mkdir(parents=True, exist_ok=True)
    validation_report_path = output_dir / "validation_report.json"
    validation_report = {
        "schema_version": "2.0",
        "dataset_id": tasks_doc["dataset_id"],
        "status": status,
        "task_count": len(tasks),
        "structural_validation": (
            "passed" if not structural_errors(tasks, contracts_doc) else "failed"
        ),
        "production_validation": (
            "passed" if not production_errors else "failed"
        ),
        "production_execution_count": len(production_rows),
        "production_execution_success_count": sum(
            row["production_execution_success"] for row in production_rows
        ),
        "production_reference_match_count": sum(
            row["production_output_matches_reference"] for row in production_rows
        ),
        "count_by_split": dict(
            sorted(Counter(task["split"] for task in tasks).items())
        ),
        "group_split_leakage_count": sum(
            1
            for group in {
                task["base_task_group_id"] for task in tasks
            }
            if len(
                {
                    task["split"]
                    for task in tasks
                    if task["base_task_group_id"] == group
                }
            )
            > 1
        ),
        "validation_errors": errors,
        "production_checks": production_rows,
        "api_model_runs_performed": False,
        "core_frozen": False,
    }
    write_json(validation_report_path, validation_report)

    generation_report_path = output_dir / "generation_report.json"
    generation_report = load_json(generation_report_path)
    generation_report["production_validation_status"] = (
        "passed" if not production_errors else "failed"
    )
    write_json(generation_report_path, generation_report)

    manifest_path = output_dir / "artifact_manifest.json"
    manifest = {
        "schema_version": "2.0",
        "dataset_id": tasks_doc["dataset_id"],
        "validation_status": status,
        "artifacts": manifest_artifacts(
            tasks_path=tasks_path,
            generation_report_path=generation_report_path,
            validation_report_path=validation_report_path,
            seeds_path=seeds_path,
            contracts_path=contracts_path,
        ),
    }
    write_json(manifest_path, manifest)
    if errors:
        raise ValueError("; ".join(errors))
    return validation_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "e1b_taskset_v2_20260730",
    )
    parser.add_argument(
        "--tasks",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--seeds",
        type=Path,
        default=HERE / "task_seeds_v2.json",
    )
    parser.add_argument(
        "--contracts",
        type=Path,
        default=VERIFIED_DIR / "contracts_v1.json",
    )
    args = parser.parse_args()
    tasks_path = args.tasks or args.output_dir / "e1b_tasks_v2.json"
    report = validate_package(
        tasks_path,
        args.seeds,
        args.contracts,
        args.output_dir,
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
