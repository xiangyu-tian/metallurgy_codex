"""Validate E1c tasks, production executions, and five-tool schemas."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parents[1]
PROJECT_ROOT = HERE.parents[2]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from core_freeze.e1b_pilot.e1b_scoring import score_answer  # noqa: E402
from core_freeze.e1b_v2.apply_candidate_gate_policy import (  # noqa: E402
    file_hash,
    load_json,
    write_json,
)
from core_freeze.e1c_end_to_end.generate_e1c_tasks import (  # noqa: E402
    POLICY_SHA256,
    project_relative,
    structural_errors,
)
from models_core.llm_adapters import model_tools  # noqa: E402
from models_core.registry import ModelRegistry  # noqa: E402


TOOL_IDS = ["A001", "A002", "A003", "A004", "B019"]


def validate_production(
    tasks: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    registry = ModelRegistry()
    discovered = registry.discover()
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    for task in tasks:
        tool_id = task["source_tool_id"]
        params = task["expected_parameters"]
        validation = registry.validate(tool_id, params)
        result = registry.invoke(tool_id, params)
        score = (
            score_answer(result.result, task["scoring_rule"])
            if result.success
            else {"correct": False}
        )
        row = {
            "task_id": task["task_id"],
            "split": task["split"],
            "tool_id": tool_id,
            "policy_action": task["frozen_policy_decision"]["action"],
            "input_validation_passed": validation["valid"],
            "production_execution_success": result.success,
            "production_output_matches_reference": bool(score["correct"]),
            "error_code": result.error_code or "",
            "error": result.error or "",
        }
        rows.append(row)
        if not validation["valid"]:
            errors.append(
                f"{task['task_id']}: input rejected: {validation['errors']}"
            )
        if not result.success:
            errors.append(
                f"{task['task_id']}: execution failed: "
                f"{result.error_code}: {result.error}"
            )
        elif not score["correct"]:
            errors.append(f"{task['task_id']}: output/reference mismatch")
    if discovered < 5:
        errors.append(f"registry discovered only {discovered} tools")

    schemas = model_tools(registry, TOOL_IDS)
    schema_names = [
        row.get("function", {}).get("name") for row in schemas
    ]
    if schema_names != TOOL_IDS:
        errors.append(f"unexpected five-tool schema order: {schema_names}")
    for schema in schemas:
        function = schema.get("function", {})
        parameters = function.get("parameters", {})
        if parameters.get("type") != "object":
            errors.append(f"{function.get('name')}: parameters not object")
        required = parameters.get("required")
        if not isinstance(required, list) or not required:
            errors.append(f"{function.get('name')}: required fields missing")
    return errors, rows, schemas


def validate_package(
    tasks_path: Path,
    seeds_path: Path,
    contracts_path: Path,
    policy_path: Path,
    e1b_tasks_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    tasks_doc = load_json(tasks_path)
    contracts = load_json(contracts_path)
    e1b_doc = load_json(e1b_tasks_path)
    tasks = tasks_doc["tasks"]
    e1b_groups = {
        task["base_task_group_id"] for task in e1b_doc["tasks"]
    }
    errors = structural_errors(tasks, contracts, e1b_groups)
    if tasks_doc.get("task_count") != 60:
        errors.append("task_count must equal 60")
    if tasks_doc.get("dataset_status") != "prepared_pre_api":
        errors.append("dataset_status must be prepared_pre_api")
    if tasks_doc.get("evaluation_split_opened") is not False:
        errors.append("evaluation split must remain sealed")
    if tasks_doc.get("frozen_policy_sha256") != POLICY_SHA256:
        errors.append("document policy hash mismatch")
    if tasks_doc.get("protocol_sha256") != file_hash(HERE / "protocol_v1.md"):
        errors.append("document protocol hash mismatch")
    if file_hash(policy_path) != POLICY_SHA256:
        errors.append("policy source hash mismatch")
    problem_texts = [task["problem_text"] for task in tasks]
    if len(problem_texts) != len(set(problem_texts)):
        errors.append("duplicate problem text")

    production_errors, production_rows, schemas = validate_production(tasks)
    errors.extend(production_errors)
    status = "passed" if not errors else "failed"

    output_dir.mkdir(parents=True, exist_ok=True)
    checks_path = output_dir / "production_checks.csv"
    with checks_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(production_rows[0]))
        writer.writeheader()
        writer.writerows(production_rows)
    schemas_path = output_dir / "five_tool_schema_snapshot.json"
    write_json(
        schemas_path,
        {
            "schema_version": "1.0",
            "tool_ids": TOOL_IDS,
            "tool_count": len(schemas),
            "tools": schemas,
        },
    )

    report_path = output_dir / "validation_report.json"
    report = {
        "schema_version": "1.0",
        "dataset_id": tasks_doc["dataset_id"],
        "status": status,
        "task_count": len(tasks),
        "production_execution_count": len(production_rows),
        "production_execution_success_count": sum(
            row["production_execution_success"] for row in production_rows
        ),
        "production_reference_match_count": sum(
            row["production_output_matches_reference"]
            for row in production_rows
        ),
        "five_tool_schema_count": len(schemas),
        "five_tool_schema_names": [
            row["function"]["name"] for row in schemas
        ],
        "count_by_split": dict(
            sorted(Counter(task["split"] for task in tasks).items())
        ),
        "call_action_count_by_split": {
            split: sum(
                task["split"] == split
                and task["frozen_policy_decision"]["action"]
                == "CALL_VERIFIED_TOOL"
                for task in tasks
            )
            for split in ("runner_development", "end_to_end_evaluation")
        },
        "e1b_group_overlap_count": 0,
        "validation_errors": errors,
        "api_model_runs_performed": False,
        "evaluation_split_opened": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    write_json(report_path, report)

    generation_report_path = output_dir / "generation_report.json"
    generation_report = load_json(generation_report_path)
    generation_report["production_validation_status"] = (
        "passed" if not production_errors else "failed"
    )
    write_json(generation_report_path, generation_report)

    manifest_path = output_dir / "artifact_manifest.json"
    artifacts = [
        tasks_path,
        generation_report_path,
        report_path,
        checks_path,
        schemas_path,
    ]
    manifest = {
        "schema_version": "1.0",
        "dataset_id": tasks_doc["dataset_id"],
        "validation_status": status,
        "artifacts": [
            {"filename": path.name, "sha256": file_hash(path)}
            for path in artifacts
        ],
        "source_artifacts": [
            {
                "filename": project_relative(HERE / "protocol_v1.md"),
                "sha256": file_hash(HERE / "protocol_v1.md"),
            },
            {
                "filename": project_relative(seeds_path),
                "sha256": file_hash(seeds_path),
            },
            {
                "filename": project_relative(contracts_path),
                "sha256": file_hash(contracts_path),
            },
            {
                "filename": project_relative(policy_path),
                "sha256": file_hash(policy_path),
            },
            {
                "filename": project_relative(e1b_tasks_path),
                "sha256": file_hash(e1b_tasks_path),
            },
            {
                "filename": project_relative(Path(__file__)),
                "sha256": file_hash(Path(__file__)),
            },
            {
                "filename": project_relative(HERE / "generate_e1c_tasks.py"),
                "sha256": file_hash(HERE / "generate_e1c_tasks.py"),
            },
        ],
        "api_model_runs_performed": False,
        "evaluation_split_opened": False,
        "core_frozen": False,
    }
    write_json(manifest_path, manifest)
    if errors:
        raise ValueError("; ".join(errors))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "e1c_taskset_v1_20260731",
    )
    parser.add_argument("--tasks", type=Path)
    parser.add_argument(
        "--seeds",
        type=Path,
        default=HERE / "task_seeds_v1.json",
    )
    parser.add_argument(
        "--contracts",
        type=Path,
        default=HERE.parent / "verified_core" / "contracts_v1.json",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=HERE.parent / "e1b_v2" / "candidate_gate_policy_v1.json",
    )
    parser.add_argument(
        "--e1b-tasks",
        type=Path,
        default=(
            PROJECT_ROOT
            / "outputs"
            / "e1b_taskset_v2_20260730"
            / "e1b_tasks_v2.json"
        ),
    )
    args = parser.parse_args()
    tasks_path = args.tasks or args.output_dir / "e1c_tasks_v1.json"
    report = validate_package(
        tasks_path,
        args.seeds,
        args.contracts,
        args.policy,
        args.e1b_tasks,
        args.output_dir,
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
