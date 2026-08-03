"""Run explicitly authorized R2/R3 E2 variability repeats."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parents[1]
PROJECT_ROOT = HERE.parents[2]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from core_freeze.e2_contract_boundaries import (  # noqa: E402
    run_e2_independent_validation as base,
)
from core_freeze.e2_contract_boundaries.run_e2_development import (  # noqa: E402
    DeepSeekOpenAIAdapter,
    file_hash,
    load_json,
)


CONFIG_PATH = HERE / "run_config_e2_variability_r2_r3_v1.json"
AUTHORIZATION_PATH = HERE / "execution_authorization_e2_variability_r2_r3_v1.json"
R1_RUN_DIR = (
    PROJECT_ROOT / "outputs" / "v11_cf04_e2_independent_validation_v1_20260803"
)
R1_RUN_MANIFEST_PATH = R1_RUN_DIR / "artifact_manifest.json"
R1_RUN_REPORT_PATH = R1_RUN_DIR / "run_report.json"
R1_ANALYSIS_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_independent_validation_analysis_v1_20260803"
)
R1_ANALYSIS_MANIFEST_PATH = R1_ANALYSIS_DIR / "artifact_manifest.json"
R1_ANALYSIS_REPORT_PATH = R1_ANALYSIS_DIR / "analysis_report.json"


def _run_id() -> str:
    return f"CF08-E2-VARIABILITY-R2-R3-{uuid.uuid4().hex[:16].upper()}"


def validate_static_bindings(config: dict[str, Any]) -> None:
    expected_paths = {
        "validation_manifest_sha256": base.VALIDATION_MANIFEST_PATH,
        "contracts_sha256": base.CONTRACTS_PATH,
        "base_policy_sha256": base.BASE_POLICY_PATH,
        "hybrid_policy_sha256": base.HYBRID_POLICY_PATH,
        "base_validation_runner_sha256": Path(base.__file__),
        "r1_run_manifest_sha256": R1_RUN_MANIFEST_PATH,
        "r1_analysis_manifest_sha256": R1_ANALYSIS_MANIFEST_PATH,
        "r1_run_report_sha256": R1_RUN_REPORT_PATH,
        "r1_analysis_report_sha256": R1_ANALYSIS_REPORT_PATH,
    }
    for field, path in expected_paths.items():
        if config[field] != file_hash(path):
            raise ValueError(f"variability config binding mismatch: {field}")
    conditions = {
        row["condition_id"]: row for row in config["conditions"]
    }
    if tuple(conditions) != base.CONDITION_ORDER:
        raise ValueError("variability condition order is not frozen")
    condition_paths = {
        "flags_only_v1_1": (
            base.BASELINE_PROMPTS_PATH,
            base.BASELINE_SCHEMA_PATH,
        ),
        "hybrid_semantic_v1_4": (
            base.HYBRID_PROMPTS_PATH,
            base.HYBRID_SCHEMA_PATH,
        ),
    }
    for condition_id, (prompt_path, schema_path) in condition_paths.items():
        condition = conditions[condition_id]
        if condition["prompt_sha256"] != file_hash(prompt_path):
            raise ValueError(f"variability prompt mismatch: {condition_id}")
        if condition["output_schema_sha256"] != file_hash(schema_path):
            raise ValueError(f"variability schema mismatch: {condition_id}")
    if config["repeat_ids"] != [2, 3]:
        raise ValueError("variability repeat IDs must be R2 and R3")
    if config["additional_repeat_count"] != 2:
        raise ValueError("variability additional repeat count must be two")
    if config["authorized_model_cell_count"] != 160:
        raise ValueError("variability run must contain 160 model cells")
    if config["tool_access"] != "disabled":
        raise ValueError("metallurgical tool access must remain disabled")
    if config["gold_labels_sent"] is not False:
        raise ValueError("gold labels cannot be sent")
    if config["mutation_history_sent"] is not False:
        raise ValueError("mutation history cannot be sent")
    if config["repeat_units_are_independent_tasks"] is not False:
        raise ValueError("repeat units cannot be treated as independent tasks")
    if config["post_validation_policy_revision_allowed"] is not False:
        raise ValueError("post-validation policy revision must remain forbidden")


def expected_authorization(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision": "authorized_to_execute_cf08_e2_variability_r2_r3_v1",
        "run_config_id": config["run_config_id"],
        "dataset_id": config["dataset_id"],
        "authorized_task_count": config["task_count"],
        "authorized_condition_count": config["condition_count"],
        "authorized_repeat_ids": config["repeat_ids"],
        "authorized_model_cell_count": config["authorized_model_cell_count"],
        "endpoint": config["openai_base_url"],
        "model": config["model"],
        "tool_access": config["tool_access"],
        "opened_validation_reuse": config["opened_validation_reuse"],
        "task_source_sha256": config["task_source_sha256"],
        "validation_manifest_sha256": config["validation_manifest_sha256"],
        "run_config_sha256": file_hash(CONFIG_PATH),
        "runner_sha256": file_hash(Path(__file__)),
        "r1_run_manifest_sha256": config["r1_run_manifest_sha256"],
        "r1_analysis_manifest_sha256": config[
            "r1_analysis_manifest_sha256"
        ],
        "baseline_prompt_sha256": config["conditions"][0][
            "prompt_sha256"
        ],
        "hybrid_prompt_sha256": config["conditions"][1][
            "prompt_sha256"
        ],
    }


def validate_execution_authorization(
    authorization: dict[str, Any],
    config: dict[str, Any],
) -> None:
    for field, expected in expected_authorization(config).items():
        if authorization.get(field) != expected:
            raise ValueError(f"variability authorization mismatch: {field}")
    if authorization.get("external_data_sharing_authorized") is not True:
        raise ValueError("variability external sharing is not authorized")
    if authorization.get("gold_labels_sent") is not False:
        raise ValueError("authorization cannot permit gold-label sharing")
    if authorization.get("mutation_history_sent") is not False:
        raise ValueError("authorization cannot permit mutation-history sharing")
    if authorization.get("repeat_units_are_independent_tasks") is not False:
        raise ValueError("authorization cannot treat repeats as independent")
    if authorization.get("post_validation_policy_revision_allowed") is not False:
        raise ValueError("authorization cannot permit post-validation revision")
    if authorization.get("confirmatory_inference_allowed") is not False:
        raise ValueError("variability pilot is not confirmatory")
    if authorization.get("core_frozen") is not False:
        raise ValueError("variability authorization cannot freeze core")


def load_authorized_inputs() -> dict[str, Any]:
    """Validate authorization before reading the opened validation task file."""
    config = load_json(CONFIG_PATH)
    validate_static_bindings(config)
    if not AUTHORIZATION_PATH.exists():
        raise FileNotFoundError("CF-08 E2 R2/R3 execution authorization is pending")
    authorization = load_json(AUTHORIZATION_PATH)
    validate_execution_authorization(authorization, config)
    if file_hash(base.TASKS_PATH) != config["task_source_sha256"]:
        raise ValueError("variability task source hash mismatch")
    tasks = load_json(base.TASKS_PATH)
    if tasks.get("dataset_id") != config["dataset_id"]:
        raise ValueError("variability dataset ID mismatch")
    if tasks.get("task_count") != config["task_count"]:
        raise ValueError("variability task count mismatch")
    return {
        "config": config,
        "authorization": authorization,
        "tasks": tasks,
        "contracts": load_json(base.CONTRACTS_PATH),
        "base_policy": load_json(base.BASE_POLICY_PATH),
        "hybrid_policy": load_json(base.HYBRID_POLICY_PATH),
        "baseline_prompts": load_json(base.BASELINE_PROMPTS_PATH),
        "baseline_schema": load_json(base.BASELINE_SCHEMA_PATH),
        "hybrid_prompts": load_json(base.HYBRID_PROMPTS_PATH),
        "hybrid_schema": load_json(base.HYBRID_SCHEMA_PATH),
    }


def execute_variability(adapter, values: dict[str, Any]) -> list[dict[str, Any]]:
    config = values["config"]
    conditions = {
        row["condition_id"]: row for row in config["conditions"]
    }
    contracts = {
        row["tool_id"]: row for row in values["contracts"]["contracts"]
    }
    records: list[dict[str, Any]] = []
    for repeat_id in config["repeat_ids"]:
        for task in values["tasks"]["tasks"]:
            contract = contracts[task["source_tool_id"]]
            baseline = base.run_flags_only_cell(
                task=task,
                contract=contract,
                prompts=values["baseline_prompts"],
                output_schema=values["baseline_schema"],
                policy=values["base_policy"],
                config=base._provider_config(  # noqa: SLF001
                    config,
                    conditions["flags_only_v1_1"],
                ),
                adapter=adapter,
            )
            baseline["condition"] = "flags_only_v1_1"
            baseline["model_run_repeat"] = repeat_id
            baseline["cell_id"] = (
                f"{task['task_id']}::flags_only_v1_1::R{repeat_id}"
            )
            records.append(baseline)
            hybrid = base.run_hybrid_cell(
                task=task,
                contract=contract,
                prompts=values["hybrid_prompts"],
                output_schema=values["hybrid_schema"],
                base_policy=values["base_policy"],
                hybrid_policy=values["hybrid_policy"],
                config=base._provider_config(  # noqa: SLF001
                    config,
                    conditions["hybrid_semantic_v1_4"],
                ),
                adapter=adapter,
            )
            hybrid["condition"] = "hybrid_semantic_v1_4"
            hybrid["model_run_repeat"] = repeat_id
            hybrid["cell_id"] = (
                f"{task['task_id']}::hybrid_semantic_v1_4::R{repeat_id}"
            )
            records.append(hybrid)
    if len(records) != config["authorized_model_cell_count"]:
        raise RuntimeError("variability model cell count mismatch")
    return records


def summarize(records: list[dict[str, Any]], values: dict[str, Any]) -> dict[str, Any]:
    repeat_summaries = {}
    for repeat_id in values["config"]["repeat_ids"]:
        subset = [
            row for row in records if row["model_run_repeat"] == repeat_id
        ]
        repeat_summaries[str(repeat_id)] = base.summarize(
            subset,
            values["base_policy"],
        )
    return {
        "status": (
            "completed"
            if len(records) == 160
            and all(row["status"] == "completed" for row in records)
            else "completed_with_provider_failures"
        ),
        "cell_count": len(records),
        "task_count": values["config"]["task_count"],
        "repeat_ids": values["config"]["repeat_ids"],
        "repeat_summaries": repeat_summaries,
        "repeat_units_are_independent_tasks": False,
        "post_validation_policy_revision_allowed": False,
        "confirmatory_inference_allowed": False,
    }


def write_outputs(
    output_dir: Path,
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    values: dict[str, Any],
    adapter_configuration: dict[str, Any],
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    run_id = _run_id()
    for record in records:
        record["run_id"] = run_id
    records_path = output_dir / "run_records.jsonl"
    records_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
        encoding="utf-8",
    )
    snapshots = {
        base.TASKS_PATH: output_dir / "opened_task_source_snapshot.json",
        base.VALIDATION_MANIFEST_PATH: (
            output_dir / "validation_candidate_manifest_snapshot.json"
        ),
        base.CONTRACTS_PATH: output_dir / "contracts_snapshot.json",
        base.BASE_POLICY_PATH: output_dir / "base_policy_snapshot.json",
        base.HYBRID_POLICY_PATH: output_dir / "hybrid_policy_snapshot.json",
        base.BASELINE_PROMPTS_PATH: output_dir / "baseline_prompt_snapshot.json",
        base.BASELINE_SCHEMA_PATH: output_dir / "baseline_schema_snapshot.json",
        base.HYBRID_PROMPTS_PATH: output_dir / "hybrid_prompt_snapshot.json",
        base.HYBRID_SCHEMA_PATH: output_dir / "hybrid_schema_snapshot.json",
        R1_RUN_MANIFEST_PATH: output_dir / "r1_run_manifest_snapshot.json",
        R1_ANALYSIS_MANIFEST_PATH: (
            output_dir / "r1_analysis_manifest_snapshot.json"
        ),
        CONFIG_PATH: output_dir / "run_config_snapshot.json",
        AUTHORIZATION_PATH: output_dir / "execution_authorization_snapshot.json",
        Path(__file__): output_dir / "runner_source_snapshot.py",
    }
    for source, target in snapshots.items():
        shutil.copyfile(source, target)
    report = {
        "schema_version": "1.0-candidate",
        "run_id": run_id,
        "run_config_id": values["config"]["run_config_id"],
        "dataset_id": values["config"]["dataset_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "adapter_configuration": adapter_configuration,
        "summary": summary,
        "opened_validation_reuse": "variability_estimation_only",
        "gold_labels_sent": False,
        "mutation_history_sent": False,
        "tool_access": "disabled",
        "post_validation_policy_revision_allowed": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    report_path = output_dir / "run_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    artifacts = [records_path, report_path, *snapshots.values()]
    manifest = {
        "schema_version": "1.0-candidate",
        "run_id": run_id,
        "artifacts": [
            {"filename": path.name, "sha256": file_hash(path)}
            for path in artifacts
        ],
        "external_api_calls": len(records),
        "external_api_execution_authorized": True,
        "repeat_units_are_independent_tasks": False,
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
    if args.output_dir.exists():
        raise FileExistsError(f"output directory already exists: {args.output_dir}")
    values = load_authorized_inputs()
    config = values["config"]
    adapter = DeepSeekOpenAIAdapter.from_environment()
    adapter.timeout = float(config["timeout_seconds"])
    if adapter.model != config["model"]:
        raise RuntimeError("configured model mismatch")
    if adapter.base_url != config["openai_base_url"]:
        raise RuntimeError("configured base URL mismatch")
    if adapter.thinking != config["thinking"]:
        raise RuntimeError("configured thinking mismatch")
    adapter.ensure_ready()
    records = execute_variability(adapter, values)
    summary = summarize(records, values)
    report = write_outputs(
        args.output_dir,
        records,
        summary,
        values,
        adapter.configuration(),
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
