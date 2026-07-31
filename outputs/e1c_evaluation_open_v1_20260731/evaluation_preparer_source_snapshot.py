"""Open and freeze the E1c evaluation snapshot without executing model calls."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[2]
EXPECTED_SOURCE_SHA256 = (
    "4e079bab547df3e762b06a765f386e47f7fbdf370093bcc587b9395c968a97cc"
)
EXPECTED_DEVELOPMENT_RUN_ID = "E1C-RUN-71BA08D38E474CB4"
EXPECTED_DEVELOPMENT_COMMIT = "dd04b1cf904892452067b73c289dc5a5b6bad8d1"
EXPECTED_TOOL_COUNTS = {
    "A001": 6,
    "A002": 6,
    "A003": 12,
    "A004": 8,
    "B019": 4,
}
EXPECTED_ACTION_COUNTS = {
    "ANSWER_WITHOUT_TOOL": 26,
    "CALL_VERIFIED_TOOL": 10,
}

try:
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
    from core_freeze.e1b_v2.apply_candidate_gate_policy import (
        file_hash,
        load_json,
        write_json,
    )


def project_relative(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def verify_manifest(directory: Path, manifest: dict[str, Any]) -> None:
    for row in manifest["artifacts"]:
        artifact = directory / row["filename"]
        if not artifact.is_file():
            raise ValueError(f"development artifact missing: {artifact.name}")
        if file_hash(artifact) != row["sha256"]:
            raise ValueError(
                f"development artifact hash mismatch: {artifact.name}"
            )


def prepare_evaluation(
    *,
    source_tasks_path: Path,
    protocol_path: Path,
    prompts_path: Path,
    config_path: Path,
    policy_path: Path,
    development_report_path: Path,
    development_manifest_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    source = load_json(source_tasks_path)
    prompts = load_json(prompts_path)
    config = load_json(config_path)
    development_report = load_json(development_report_path)
    development_manifest = load_json(development_manifest_path)

    if file_hash(source_tasks_path) != EXPECTED_SOURCE_SHA256:
        raise ValueError("source taskset hash differs from frozen E1c v1")
    if source.get("evaluation_split_opened") is not False:
        raise ValueError("source taskset must be sealed before preparation")
    if config.get("selected_split") != "end_to_end_evaluation":
        raise ValueError("evaluation config selects the wrong split")
    if config.get("evaluation_split_opened") is not True:
        raise ValueError("evaluation config does not open the split")
    if config.get("requires_external_api_authorization") is not True:
        raise ValueError("evaluation config must require API authorization")
    if config.get("policy_revision_allowed") is not False:
        raise ValueError("evaluation config permits policy revision")
    if config.get("confirmatory_inference_allowed") is not False:
        raise ValueError("E1c evaluation cannot claim confirmatory inference")
    if file_hash(protocol_path) != config.get("protocol_sha256"):
        raise ValueError("protocol hash mismatch")
    if file_hash(prompts_path) != config.get("prompt_sha256"):
        raise ValueError("prompt hash mismatch")
    if file_hash(policy_path) != config.get("frozen_policy_sha256"):
        raise ValueError("policy hash mismatch")
    if prompts.get("prompt_version") != config.get("prompt_version"):
        raise ValueError("prompt version mismatch")

    if development_report.get("run_id") != EXPECTED_DEVELOPMENT_RUN_ID:
        raise ValueError("unexpected development run id")
    if config.get("development_run_id") != EXPECTED_DEVELOPMENT_RUN_ID:
        raise ValueError("config development run id mismatch")
    if config.get("development_git_commit") != EXPECTED_DEVELOPMENT_COMMIT:
        raise ValueError("config development commit mismatch")
    summary = development_report.get("summary", {})
    if summary.get("status") != "completed":
        raise ValueError("development run did not complete")
    if summary.get("cell_count") != 144:
        raise ValueError("development run does not contain 144 cells")
    if development_report.get("evaluation_split_opened") is not False:
        raise ValueError("development report already opens evaluation")
    if development_report.get("confirmatory_inference_allowed") is not False:
        raise ValueError("development report permits confirmatory inference")
    if development_manifest.get("run_id") != EXPECTED_DEVELOPMENT_RUN_ID:
        raise ValueError("development manifest run id mismatch")
    verify_manifest(development_manifest_path.parent, development_manifest)

    tasks = [
        task
        for task in source["tasks"]
        if task.get("split") == "end_to_end_evaluation"
    ]
    if len(tasks) != 36:
        raise ValueError(f"expected 36 evaluation tasks, found {len(tasks)}")
    tool_counts = dict(
        sorted(Counter(task["source_tool_id"] for task in tasks).items())
    )
    action_counts = dict(
        sorted(
            Counter(
                task["frozen_policy_decision"]["action"] for task in tasks
            ).items()
        )
    )
    if tool_counts != EXPECTED_TOOL_COUNTS:
        raise ValueError("evaluation tool counts differ from frozen design")
    if action_counts != EXPECTED_ACTION_COUNTS:
        raise ValueError("evaluation action counts differ from frozen design")

    output_dir.mkdir(parents=True, exist_ok=False)
    tasks_path = output_dir / "e1c_evaluation_tasks_v1.json"
    tasks_doc = {
        "schema_version": "1.0",
        "dataset_id": config["dataset_id"],
        "dataset_status": "opened_evaluation_pending_api_authorization",
        "source_dataset_id": source["dataset_id"],
        "source_dataset_sha256": file_hash(source_tasks_path),
        "protocol_id": config["protocol_id"],
        "protocol_sha256": config["protocol_sha256"],
        "prompt_version": prompts["prompt_version"],
        "frozen_policy_id": config["frozen_policy_id"],
        "frozen_policy_sha256": config["frozen_policy_sha256"],
        "required_split": "end_to_end_evaluation",
        "task_count": len(tasks),
        "tasks": tasks,
        "evaluation_split_opened": True,
        "external_api_execution_authorized": False,
        "api_model_runs_performed": False,
        "confirmatory_inference_allowed": False,
        "policy_revision_allowed": False,
        "core_frozen": False,
    }
    write_json(tasks_path, tasks_doc)

    runner_path = HERE / "run_e1c.py"
    scoring_path = HERE.parent / "e1b_pilot" / "e1b_scoring.py"
    opening_path = output_dir / "evaluation_opening_record.json"
    opening_record = {
        "schema_version": "1.0",
        "opening_id": "E1C-EVALUATION-OPEN-V1-20260731",
        "decision": "prepared_for_external_execution_authorization",
        "decision_basis": (
            "Complete development run passed engineering checks; user "
            "authorized local preparation of the evaluation opening package."
        ),
        "scope": "local_snapshot_preparation_only",
        "development_run_id": development_report["run_id"],
        "development_git_commit": config["development_git_commit"],
        "development_report_sha256": file_hash(development_report_path),
        "development_manifest_sha256": file_hash(development_manifest_path),
        "source_taskset_sha256": file_hash(source_tasks_path),
        "evaluation_task_snapshot_sha256": file_hash(tasks_path),
        "run_config_sha256": file_hash(config_path),
        "prompt_sha256": file_hash(prompts_path),
        "protocol_sha256": file_hash(protocol_path),
        "policy_sha256": file_hash(policy_path),
        "runner_sha256": file_hash(runner_path),
        "scoring_sha256": file_hash(scoring_path),
        "evaluation_task_count": len(tasks),
        "scheduled_cells": len(tasks) * len(config["conditions"]),
        "evaluation_split_opened": True,
        "external_api_execution_authorized": False,
        "api_model_runs_performed": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    write_json(opening_path, opening_record)

    request_path = output_dir / "execution_authorization_request.json"
    authorization_request = {
        "schema_version": "1.0",
        "request_id": "E1C-EVALUATION-EXECUTION-REQUEST-V1-20260731",
        "status": "pending_explicit_user_authorization",
        "requested_decision": "authorized_to_execute_evaluation",
        "dataset_id": config["dataset_id"],
        "run_config_id": config["run_config_id"],
        "task_snapshot_sha256": file_hash(tasks_path),
        "prompt_sha256": file_hash(prompts_path),
        "run_config_sha256": file_hash(config_path),
        "runner_sha256": file_hash(runner_path),
        "endpoint": config["openai_base_url"],
        "model": config["model"],
        "authorized_task_count": len(tasks),
        "scheduled_cells": len(tasks) * len(config["conditions"]),
        "authorized_payload_types": [
            "36 evaluation task texts",
            "frozen E1c prompt text",
            "five verified tool schemas",
            "derived tool execution results",
        ],
        "evaluation_split_opened": True,
        "external_api_execution_authorized": False,
        "api_model_runs_performed": False,
    }
    write_json(request_path, authorization_request)

    snapshots = [
        (protocol_path, output_dir / protocol_path.name),
        (prompts_path, output_dir / prompts_path.name),
        (config_path, output_dir / config_path.name),
        (policy_path, output_dir / policy_path.name),
        (runner_path, output_dir / "runner_source_snapshot.py"),
        (scoring_path, output_dir / "scoring_source_snapshot.py"),
        (
            Path(__file__),
            output_dir / "evaluation_preparer_source_snapshot.py",
        ),
        (
            development_report_path,
            output_dir / "development_run_report_snapshot.json",
        ),
        (
            development_manifest_path,
            output_dir / "development_artifact_manifest_snapshot.json",
        ),
    ]
    for source_path, target_path in snapshots:
        target_path.write_bytes(source_path.read_bytes())

    report_path = output_dir / "preparation_report.json"
    report = {
        "schema_version": "1.0",
        "opening_id": opening_record["opening_id"],
        "status": "passed",
        "task_count": len(tasks),
        "condition_count": len(config["conditions"]),
        "scheduled_cells": len(tasks) * len(config["conditions"]),
        "task_count_by_tool": tool_counts,
        "policy_action_task_counts": action_counts,
        "development_evidence_verified": True,
        "artifact_hashes_verified": True,
        "evaluation_split_opened": True,
        "external_api_execution_authorized": False,
        "api_model_runs_performed": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    write_json(report_path, report)

    artifacts = [
        tasks_path,
        opening_path,
        request_path,
        *[target for _, target in snapshots],
        report_path,
    ]
    manifest_path = output_dir / "artifact_manifest.json"
    manifest = {
        "schema_version": "1.0",
        "opening_id": opening_record["opening_id"],
        "artifacts": [
            {"filename": path.name, "sha256": file_hash(path)}
            for path in artifacts
        ],
        "source_artifacts": [
            {
                "filename": project_relative(path),
                "sha256": file_hash(path),
            }
            for path in (
                source_tasks_path,
                protocol_path,
                prompts_path,
                config_path,
                policy_path,
                runner_path,
                scoring_path,
                development_report_path,
                development_manifest_path,
                Path(__file__),
            )
        ],
        "evaluation_split_opened": True,
        "external_api_execution_authorized": False,
        "api_model_runs_performed": False,
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
        default=HERE / "run_config_evaluation_v1.json",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=HERE.parent / "e1b_v2" / "candidate_gate_policy_v1.json",
    )
    parser.add_argument(
        "--development-report",
        type=Path,
        default=(
            PROJECT_ROOT
            / "outputs"
            / "e1c_development_full_r1_20260731"
            / "run_report.json"
        ),
    )
    parser.add_argument(
        "--development-manifest",
        type=Path,
        default=(
            PROJECT_ROOT
            / "outputs"
            / "e1c_development_full_r1_20260731"
            / "artifact_manifest.json"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=(
            PROJECT_ROOT / "outputs" / "e1c_evaluation_open_v1_20260731"
        ),
    )
    args = parser.parse_args()
    report = prepare_evaluation(
        source_tasks_path=args.source_tasks,
        protocol_path=args.protocol,
        prompts_path=args.prompts,
        config_path=args.config,
        policy_path=args.policy,
        development_report_path=args.development_report,
        development_manifest_path=args.development_manifest,
        output_dir=args.output_dir,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
