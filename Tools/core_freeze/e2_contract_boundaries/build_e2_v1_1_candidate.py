"""Build and audit the E2 v1.1 flags-only candidate package."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parents[1]
PROJECT_ROOT = HERE.parents[2]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from core_freeze.e1b_pilot.e1b_scoring import extract_json_answer
from core_freeze.e2_contract_boundaries.run_e2_development import (
    CONTRACTS_PATH,
    POLICY_PATH,
    TASKS_PATH,
    file_hash,
    load_json,
    summarize,
)
from core_freeze.e2_contract_boundaries.run_e2_development_v1_1 import (
    CONFIG_PATH,
    OUTPUT_SCHEMA_PATH,
    PROMPTS_PATH,
    score_flags_prediction,
    validate_inputs,
)


AUTHORIZATION_REQUEST_PATH = (
    HERE / "execution_authorization_request_v1_1.json"
)
RUNNER_PATH = HERE / "run_e2_development_v1_1.py"
PREVIOUS_RUN_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_model_development_r1_network_retry_20260731"
)
PREVIOUS_ANALYSIS_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_model_development_analysis_20260731"
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def build_counterfactual_replay(
    *,
    previous_records: list[dict[str, Any]],
    tasks_doc: dict[str, Any],
    output_schema: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tasks = {row["task_id"]: row for row in tasks_doc["tasks"]}
    records = []
    for source in previous_records:
        task = tasks[source["task_id"]]
        extracted = extract_json_answer(source["raw_output"])
        source_answer = extracted["answer"]
        projected_output = (
            {"flags": source_answer.get("flags")}
            if isinstance(source_answer, dict)
            else source_answer
        )
        scoring = score_flags_prediction(
            projected_output,
            task,
            output_schema,
            policy,
        )
        records.append(
            {
                "task_id": task["task_id"],
                "source_tool_id": task["source_tool_id"],
                "mutation_types": task["mutation_types"],
                "expected_flags": task["expected_flags"],
                "expected_primary_status": task["primary_status"],
                "expected_action": task["policy_expected_action"],
                "source_run_id": source["run_id"],
                "source_prompt_version": source["prompt_version"],
                "source_raw_output_sha256": _text_hash(
                    source["raw_output"]
                ),
                "status": source["status"],
                "provider_attempt_count": source[
                    "provider_attempt_count"
                ],
                "parse_status": extracted["status"],
                **scoring,
            }
        )
    supported_flags = [
        flag
        for flag in policy["flags"]
        if any(flag in task["expected_flags"] for task in tasks.values())
    ]
    summary = summarize(records, supported_flags)
    return records, {
        **summary,
        "analysis_type": "retrospective_counterfactual_replay",
        "source_prompt_version": "e2-contract-readiness-v1",
        "target_output_contract": "flags_only_v1.1",
        "projection_rule": (
            "project source parsed object to its flags field only"
        ),
        "new_provider_calls": 0,
        "independent_model_recheck_completed": False,
        "confirmatory_inference_allowed": False,
    }


def _text_hash(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_candidate() -> dict[str, Any]:
    tasks_doc = load_json(TASKS_PATH)
    contracts_doc = load_json(CONTRACTS_PATH)
    prompts = load_json(PROMPTS_PATH)
    output_schema = load_json(OUTPUT_SCHEMA_PATH)
    policy = load_json(POLICY_PATH)
    config = load_json(CONFIG_PATH)
    validate_inputs(
        tasks_doc,
        contracts_doc,
        prompts,
        output_schema,
        policy,
        config,
    )
    request = load_json(AUTHORIZATION_REQUEST_PATH)
    if request["status"] != "awaiting_explicit_user_authorization":
        raise ValueError("v1.1 authorization request must remain pending")
    if request["execution_authorization_file_exists"] is not False:
        raise ValueError("v1.1 must not claim execution authorization")
    if (HERE / request["execution_authorization_file"]).exists():
        raise ValueError("unexpected v1.1 execution authorization file")
    prompt_text = json.dumps(prompts, ensure_ascii=False)
    for forbidden in ("mutation_types", "expected_flags", "task_id"):
        if forbidden in prompt_text:
            raise ValueError(f"prompt leaks forbidden field: {forbidden}")
    return {
        "tasks_doc": tasks_doc,
        "contracts_doc": contracts_doc,
        "prompts": prompts,
        "output_schema": output_schema,
        "policy": policy,
        "config": config,
        "authorization_request": request,
    }


def build_package(output_dir: Path) -> dict[str, Any]:
    values = validate_candidate()
    previous_records = load_jsonl(
        PREVIOUS_RUN_DIR / "run_records.jsonl"
    )
    replay_records, replay_summary = build_counterfactual_replay(
        previous_records=previous_records,
        tasks_doc=values["tasks_doc"],
        output_schema=values["output_schema"],
        policy=values["policy"],
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    snapshots = {
        PROMPTS_PATH: output_dir / "prompt_candidate.json",
        OUTPUT_SCHEMA_PATH: output_dir / "output_schema_candidate.json",
        CONFIG_PATH: output_dir / "run_config_candidate.json",
        AUTHORIZATION_REQUEST_PATH: (
            output_dir / "execution_authorization_request.json"
        ),
        RUNNER_PATH: output_dir / "runner_candidate.py",
    }
    for source, target in snapshots.items():
        shutil.copyfile(source, target)
    replay_path = output_dir / "counterfactual_replay_records.jsonl"
    with replay_path.open("x", encoding="utf-8", newline="\n") as stream:
        for record in replay_records:
            stream.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )
    replay_report_path = output_dir / "counterfactual_replay_report.json"
    replay_report_path.write_text(
        json.dumps(replay_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    previous_report = load_json(PREVIOUS_RUN_DIR / "run_report.json")
    previous_analysis = load_json(
        PREVIOUS_ANALYSIS_DIR / "analysis_report.json"
    )
    report = {
        "schema_version": "1.1",
        "candidate_id": "E2-FLAGS-ONLY-POLICY-CANDIDATE-V1.1-20260731",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "prepared_not_authorized",
        "design_changes": [
            "model outputs only bottom-level flags",
            "primary_status is deterministically derived from flags",
            "action is deterministically derived from flags",
            "prompt distinguishes unsupported system from in-system OOD",
            "prompt requires complete multi-label retention",
        ],
        "unchanged_components": {
            "dataset_id": values["tasks_doc"]["dataset_id"],
            "task_count": values["tasks_doc"]["task_count"],
            "readiness_rule_version": values["policy"][
                "readiness_rule_version"
            ],
            "provider": values["config"]["provider"],
            "model": values["config"]["model"],
            "tool_access": values["config"]["tool_access"],
        },
        "previous_run": {
            "run_id": previous_report["run_id"],
            "strict_summary": previous_report["summary"],
            "parsed_field_diagnostic": previous_analysis[
                "parsed_field_diagnostic"
            ],
        },
        "counterfactual_replay": replay_summary,
        "execution_gate": {
            "authorization_status": "pending",
            "new_provider_calls": 0,
            "independent_model_recheck_completed": False,
        },
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    report_path = output_dir / "candidate_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    artifacts = list(snapshots.values()) + [
        replay_path,
        replay_report_path,
        report_path,
    ]
    manifest = {
        "schema_version": "1.1",
        "candidate_id": report["candidate_id"],
        "source_bindings": {
            "task_source_sha256": file_hash(TASKS_PATH),
            "contracts_sha256": file_hash(CONTRACTS_PATH),
            "policy_sha256": file_hash(POLICY_PATH),
            "previous_run_manifest_sha256": file_hash(
                PREVIOUS_RUN_DIR / "artifact_manifest.json"
            ),
            "previous_analysis_manifest_sha256": file_hash(
                PREVIOUS_ANALYSIS_DIR / "artifact_manifest.json"
            ),
            "builder_sha256": file_hash(Path(__file__)),
        },
        "artifacts": [
            {"filename": path.name, "sha256": file_hash(path)}
            for path in artifacts
        ],
        "execution_status": "prepared_not_authorized",
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    (output_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = build_package(args.output_dir.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
