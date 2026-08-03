"""Run an explicitly authorized E2 held-out baseline/hybrid comparison."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parents[1]
PROJECT_ROOT = HERE.parents[2]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from core_freeze.e2_contract_boundaries.run_e2_development import (  # noqa: E402
    DeepSeekOpenAIAdapter,
    file_hash,
    load_json,
)
from core_freeze.e2_contract_boundaries.run_e2_development_v1_1 import (  # noqa: E402
    run_cell as run_flags_only_cell,
)
from core_freeze.e2_contract_boundaries.run_e2_hybrid_semantic_development import (  # noqa: E402
    run_cell as run_hybrid_cell,
)


VALIDATION_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_independent_validation_v1_candidate_20260731"
)
VALIDATION_MANIFEST_PATH = VALIDATION_DIR / "artifact_manifest.json"
TASKS_PATH = VALIDATION_DIR / "e2_validation_tasks_v1.json"
CONTRACTS_PATH = HERE.parent / "verified_core" / "contracts_v1.json"
BASE_POLICY_PATH = HERE / "policy_v1.json"
HYBRID_POLICY_PATH = HERE / "hybrid_gate_policy_v1.json"
BASELINE_PROMPTS_PATH = HERE / "prompts_v1_1.json"
BASELINE_SCHEMA_PATH = HERE / "output_schema_v1_1.json"
HYBRID_PROMPTS_PATH = HERE / "prompts_hybrid_semantic_v1_4.json"
HYBRID_SCHEMA_PATH = HERE / "output_schema_hybrid_semantic_v1.json"
CONFIG_PATH = HERE / "run_config_independent_validation_v1.json"
AUTHORIZATION_PATH = HERE / "execution_authorization_independent_validation_v1.json"

CONDITION_ORDER = ("flags_only_v1_1", "hybrid_semantic_v1_4")


def _run_id() -> str:
    return f"E2-INDEPENDENT-VALIDATION-{uuid.uuid4().hex[:16].upper()}"


def validate_static_bindings(config: dict[str, Any]) -> None:
    expected_hashes = {
        "validation_manifest_sha256": VALIDATION_MANIFEST_PATH,
        "contracts_sha256": CONTRACTS_PATH,
        "base_policy_sha256": BASE_POLICY_PATH,
        "hybrid_policy_sha256": HYBRID_POLICY_PATH,
    }
    for field, path in expected_hashes.items():
        if config[field] != file_hash(path):
            raise ValueError(f"run config binding mismatch: {field}")
    conditions = {
        row["condition_id"]: row for row in config["conditions"]
    }
    if tuple(conditions) != CONDITION_ORDER:
        raise ValueError("validation condition order is not frozen")
    condition_paths = {
        "flags_only_v1_1": (
            BASELINE_PROMPTS_PATH,
            BASELINE_SCHEMA_PATH,
        ),
        "hybrid_semantic_v1_4": (
            HYBRID_PROMPTS_PATH,
            HYBRID_SCHEMA_PATH,
        ),
    }
    for condition_id, (prompt_path, schema_path) in condition_paths.items():
        condition = conditions[condition_id]
        if condition["prompt_sha256"] != file_hash(prompt_path):
            raise ValueError(f"prompt binding mismatch: {condition_id}")
        if condition["output_schema_sha256"] != file_hash(schema_path):
            raise ValueError(f"schema binding mismatch: {condition_id}")
    if config["task_count"] != 40:
        raise ValueError("independent validation task count must be 40")
    if config["condition_count"] != 2:
        raise ValueError("independent validation condition count must be 2")
    if config["model_run_repeats"] != 1:
        raise ValueError("initial independent validation repeat count must be 1")
    if config["authorized_model_cell_count"] != 80:
        raise ValueError("independent validation must contain 80 model cells")
    if config["tool_access"] != "disabled":
        raise ValueError("metallurgical tool access must remain disabled")
    if config["gold_labels_sent"] is not False:
        raise ValueError("gold labels cannot be sent")
    if config["mutation_history_sent"] is not False:
        raise ValueError("mutation history cannot be sent")


def expected_authorization(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision": "authorized_to_execute_e2_independent_validation_v1",
        "run_config_id": config["run_config_id"],
        "dataset_id": config["dataset_id"],
        "authorized_task_count": config["task_count"],
        "authorized_condition_count": config["condition_count"],
        "authorized_repeats": config["model_run_repeats"],
        "authorized_model_cell_count": config["authorized_model_cell_count"],
        "endpoint": config["openai_base_url"],
        "model": config["model"],
        "tool_access": config["tool_access"],
        "validation_dataset_access": "authorized_once",
        "task_source_sha256": config["task_source_sha256"],
        "validation_manifest_sha256": config[
            "validation_manifest_sha256"
        ],
        "run_config_sha256": file_hash(CONFIG_PATH),
        "runner_sha256": file_hash(Path(__file__)),
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
            raise ValueError(f"execution authorization mismatch: {field}")
    if authorization.get("external_data_sharing_authorized") is not True:
        raise ValueError("external data sharing is not authorized")
    if authorization.get("gold_labels_sent") is not False:
        raise ValueError("authorization cannot permit gold-label sharing")
    if authorization.get("mutation_history_sent") is not False:
        raise ValueError("authorization cannot permit mutation-history sharing")
    if authorization.get("confirmatory_inference_allowed") is not False:
        raise ValueError("initial validation is not confirmatory")
    if authorization.get("core_frozen") is not False:
        raise ValueError("validation authorization cannot freeze core")


def load_authorized_inputs() -> dict[str, Any]:
    """Validate authorization before reading the held-out task file."""
    config = load_json(CONFIG_PATH)
    validate_static_bindings(config)
    if not AUTHORIZATION_PATH.exists():
        raise FileNotFoundError(
            "independent validation execution authorization is pending"
        )
    authorization = load_json(AUTHORIZATION_PATH)
    validate_execution_authorization(authorization, config)
    if file_hash(TASKS_PATH) != config["task_source_sha256"]:
        raise ValueError("held-out task source hash mismatch")
    tasks = load_json(TASKS_PATH)
    if tasks.get("dataset_id") != config["dataset_id"]:
        raise ValueError("held-out dataset ID mismatch")
    if tasks.get("task_count") != config["task_count"]:
        raise ValueError("held-out task count mismatch")
    if len(tasks.get("tasks", [])) != config["task_count"]:
        raise ValueError("held-out task array length mismatch")
    return {
        "config": config,
        "authorization": authorization,
        "tasks": tasks,
        "contracts": load_json(CONTRACTS_PATH),
        "base_policy": load_json(BASE_POLICY_PATH),
        "hybrid_policy": load_json(HYBRID_POLICY_PATH),
        "baseline_prompts": load_json(BASELINE_PROMPTS_PATH),
        "baseline_schema": load_json(BASELINE_SCHEMA_PATH),
        "hybrid_prompts": load_json(HYBRID_PROMPTS_PATH),
        "hybrid_schema": load_json(HYBRID_SCHEMA_PATH),
    }


def _provider_config(
    config: dict[str, Any],
    condition: dict[str, Any],
) -> dict[str, Any]:
    return {
        **config,
        "prompt_version": condition["prompt_version"],
        "max_tokens": condition["max_tokens"],
    }


def execute_validation(adapter, values: dict[str, Any]) -> list[dict[str, Any]]:
    config = values["config"]
    condition_configs = {
        row["condition_id"]: row for row in config["conditions"]
    }
    contracts = {
        row["tool_id"]: row for row in values["contracts"]["contracts"]
    }
    records: list[dict[str, Any]] = []
    for task in values["tasks"]["tasks"]:
        contract = contracts[task["source_tool_id"]]
        baseline = run_flags_only_cell(
            task=task,
            contract=contract,
            prompts=values["baseline_prompts"],
            output_schema=values["baseline_schema"],
            policy=values["base_policy"],
            config=_provider_config(
                config,
                condition_configs["flags_only_v1_1"],
            ),
            adapter=adapter,
        )
        baseline["condition"] = "flags_only_v1_1"
        baseline["cell_id"] = f"{task['task_id']}::flags_only_v1_1::R1"
        records.append(baseline)
        hybrid = run_hybrid_cell(
            task=task,
            contract=contract,
            prompts=values["hybrid_prompts"],
            output_schema=values["hybrid_schema"],
            base_policy=values["base_policy"],
            hybrid_policy=values["hybrid_policy"],
            config=_provider_config(
                config,
                condition_configs["hybrid_semantic_v1_4"],
            ),
            adapter=adapter,
        )
        hybrid["condition"] = "hybrid_semantic_v1_4"
        hybrid["cell_id"] = f"{task['task_id']}::hybrid_semantic_v1_4::R1"
        records.append(hybrid)
    if len(records) != config["authorized_model_cell_count"]:
        raise RuntimeError("independent validation cell count mismatch")
    return records


def _predicted_flags(record: dict[str, Any]) -> list[str]:
    if record["condition"] == "flags_only_v1_1":
        return record.get("predicted_flags") or []
    return record.get("merged_flags") or []


def _flags_exact(record: dict[str, Any]) -> bool:
    if record["condition"] == "flags_only_v1_1":
        return bool(record.get("flags_exact"))
    return bool(record.get("merged_flags_exact"))


def _condition_summary(
    records: list[dict[str, Any]],
    condition_id: str,
    flag_order: list[str],
) -> dict[str, Any]:
    subset = [row for row in records if row["condition"] == condition_id]
    metrics: dict[str, dict[str, float | int]] = {}
    for flag in flag_order:
        tp = fp = fn = 0
        for row in subset:
            expected = set(row["expected_flags"])
            predicted = set(_predicted_flags(row))
            tp += int(flag in expected and flag in predicted)
            fp += int(flag not in expected and flag in predicted)
            fn += int(flag in expected and flag not in predicted)
        denominator = 2 * tp + fp + fn
        metrics[flag] = {
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "f1": (2 * tp / denominator) if denominator else 1.0,
        }
    return {
        "condition_id": condition_id,
        "cell_count": len(subset),
        "completed_count": sum(row["status"] == "completed" for row in subset),
        "provider_failure_count": sum(
            row["status"] != "completed" for row in subset
        ),
        "flags_exact_count": sum(_flags_exact(row) for row in subset),
        "action_correct_count": sum(
            bool(row.get("action_correct")) for row in subset
        ),
        "premature_call_count": sum(
            row["expected_action"] != "call"
            and row.get("predicted_action") == "call"
            for row in subset
        ),
        "flag_macro_f1": (
            sum(float(value["f1"]) for value in metrics.values())
            / len(metrics)
        ),
        "flag_metrics": metrics,
        "predicted_action_counts": dict(
            Counter(row.get("predicted_action") for row in subset)
        ),
    }


def summarize(
    records: list[dict[str, Any]],
    base_policy: dict[str, Any],
) -> dict[str, Any]:
    summaries = {
        condition_id: _condition_summary(
            records,
            condition_id,
            list(base_policy["flags"]),
        )
        for condition_id in CONDITION_ORDER
    }
    by_key = {
        (row["task_id"], row["condition"]): row for row in records
    }
    pairs = []
    for task_id in sorted({row["task_id"] for row in records}):
        baseline = by_key[(task_id, "flags_only_v1_1")]
        hybrid = by_key[(task_id, "hybrid_semantic_v1_4")]
        pairs.append(
            {
                "task_id": task_id,
                "flags_exact_delta": int(_flags_exact(hybrid))
                - int(_flags_exact(baseline)),
                "action_correct_delta": int(bool(hybrid["action_correct"]))
                - int(bool(baseline["action_correct"])),
            }
        )
    status = (
        "completed"
        if len(records) == 80
        and all(row["status"] == "completed" for row in records)
        else "completed_with_provider_failures"
    )
    return {
        "status": status,
        "cell_count": len(records),
        "task_count": len(pairs),
        "condition_summaries": summaries,
        "paired_descriptive_differences": {
            "hybrid_minus_baseline_flags_exact": sum(
                row["flags_exact_delta"] for row in pairs
            ),
            "hybrid_minus_baseline_action_correct": sum(
                row["action_correct_delta"] for row in pairs
            ),
        },
        "model_performance_claim_allowed": True,
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
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n" for row in records
        ),
        encoding="utf-8",
    )
    snapshots = {
        TASKS_PATH: output_dir / "held_out_task_source_snapshot.json",
        VALIDATION_MANIFEST_PATH: (
            output_dir / "validation_candidate_manifest_snapshot.json"
        ),
        CONTRACTS_PATH: output_dir / "contracts_snapshot.json",
        BASE_POLICY_PATH: output_dir / "base_policy_snapshot.json",
        HYBRID_POLICY_PATH: output_dir / "hybrid_policy_snapshot.json",
        BASELINE_PROMPTS_PATH: output_dir / "baseline_prompt_snapshot.json",
        BASELINE_SCHEMA_PATH: output_dir / "baseline_schema_snapshot.json",
        HYBRID_PROMPTS_PATH: output_dir / "hybrid_prompt_snapshot.json",
        HYBRID_SCHEMA_PATH: output_dir / "hybrid_schema_snapshot.json",
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
        "validation_dataset_access": "authorized_and_executed_once",
        "gold_labels_sent": False,
        "mutation_history_sent": False,
        "tool_access": "disabled",
        "model_policy_revision_allowed_after_open": False,
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
        raise FileExistsError(
            f"output directory already exists: {args.output_dir}"
        )
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
    records = execute_validation(adapter, values)
    summary = summarize(records, values["base_policy"])
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
