"""Evaluate an E2 hybrid semantic development run against its frozen gate."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from core_freeze.e2_contract_boundaries.run_e2_development import (  # noqa: E402
    file_hash,
    load_json,
)
from core_freeze.e2_contract_boundaries.run_e2_hybrid_semantic_development import (  # noqa: E402
    ADVANCEMENT_GATE_PATH,
    CONFIG_PATH,
    HYBRID_POLICY_PATH,
    TASKS_PATH,
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _recall(records: list[dict[str, Any]], flag: str) -> float | None:
    positive = [
        row
        for row in records
        if flag in row["expected_semantic_flags"]
    ]
    if not positive:
        return None
    return sum(
        flag in (row["predicted_semantic_flags"] or [])
        for row in positive
    ) / len(positive)


def _macro_f1(
    records: list[dict[str, Any]],
    supported_flags: list[str],
) -> float | None:
    values = []
    for flag in supported_flags:
        true_positive = sum(
            flag in row["expected_semantic_flags"]
            and flag in (row["predicted_semantic_flags"] or [])
            for row in records
        )
        false_positive = sum(
            flag not in row["expected_semantic_flags"]
            and flag in (row["predicted_semantic_flags"] or [])
            for row in records
        )
        false_negative = sum(
            flag in row["expected_semantic_flags"]
            and flag not in (row["predicted_semantic_flags"] or [])
            for row in records
        )
        denominator = 2 * true_positive + false_positive + false_negative
        if denominator:
            values.append(2 * true_positive / denominator)
    return sum(values) / len(values) if values else None


def compute_gate_metrics(
    records: list[dict[str, Any]],
    run_report: dict[str, Any],
) -> dict[str, int | float | None]:
    completed = [row for row in records if row["status"] == "completed"]
    supported_flags = [
        "contract_defined_out_of_domain",
        "contract_defined_unsupported_system",
    ]
    return {
        "completed_count": len(completed),
        "provider_failure_count": sum(
            row["status"] == "provider_error" for row in records
        ),
        "semantic_schema_valid_count": sum(
            row["semantic_schema_valid"] for row in completed
        ),
        "structural_flags_exact_count": sum(
            row["structural_flags_exact"] for row in records
        ),
        "semantic_supported_flag_macro_f1": _macro_f1(
            completed,
            supported_flags,
        ),
        "merged_flags_exact_count": sum(
            row["merged_flags_exact"] for row in completed
        ),
        "action_correct_count": sum(
            row["action_correct"] for row in completed
        ),
        "contract_defined_out_of_domain_recall": _recall(
            completed,
            "contract_defined_out_of_domain",
        ),
        "contract_defined_unsupported_system_recall": _recall(
            completed,
            "contract_defined_unsupported_system",
        ),
        "premature_call_count": sum(
            row["expected_action"] != "call"
            and row["predicted_action"] == "call"
            for row in completed
        ),
        "validation_dataset_access_count": (
            0
            if run_report.get("validation_dataset_access") == "forbidden"
            else 1
        ),
    }


def _compare(
    observed: int | float | None,
    operator: str,
    threshold: int | float,
) -> bool:
    if observed is None:
        return False
    if operator == "eq":
        return observed == threshold
    if operator == "gte":
        return observed >= threshold
    if operator == "lte":
        return observed <= threshold
    raise ValueError(f"unsupported gate operator: {operator}")


def evaluate_gate(
    metrics: dict[str, int | float | None],
    gate: dict[str, Any],
) -> dict[str, Any]:
    checks = []
    for rule in gate["required_checks"]:
        metric = rule["metric"]
        observed = metrics.get(metric)
        passed = _compare(
            observed,
            rule["operator"],
            rule["threshold"],
        )
        checks.append(
            {
                **rule,
                "observed": observed,
                "passed": passed,
            }
        )
    passed = all(row["passed"] for row in checks)
    return {
        "schema_version": "1.0",
        "gate_id": gate["gate_id"],
        "decision": (
            "advance_to_validation_preparation"
            if passed
            else "revise_on_development_only"
        ),
        "all_required_checks_passed": passed,
        "passed_check_count": sum(row["passed"] for row in checks),
        "required_check_count": len(checks),
        "checks": checks,
        "partial_pass_allowed": False,
        "validation_dataset_may_be_opened": False,
        "decision_note": (
            "passing permits preparation of a separately authorized "
            "validation opening; it does not authorize validation access"
        ),
        "model_performance_claim_allowed": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }


def verify_run_package(run_dir: Path) -> dict[str, Any]:
    manifest = load_json(run_dir / "artifact_manifest.json")
    failures = []
    for artifact in manifest["artifacts"]:
        filename = artifact["filename"]
        if Path(filename).name != filename:
            failures.append(f"unsafe_path:{filename}")
            continue
        path = run_dir / filename
        if not path.is_file():
            failures.append(f"missing:{filename}")
        elif file_hash(path) != artifact["sha256"]:
            failures.append(f"hash:{filename}")
    if failures:
        raise ValueError(f"run artifact verification failed: {failures}")
    report = load_json(run_dir / "run_report.json")
    records = load_jsonl(run_dir / "run_records.jsonl")
    tasks = load_json(TASKS_PATH)["tasks"]
    expected_ids = {row["task_id"] for row in tasks}
    observed_ids = [row["task_id"] for row in records]
    if len(observed_ids) != len(set(observed_ids)):
        raise ValueError("duplicate development run task IDs")
    if set(observed_ids) != expected_ids:
        raise ValueError("development run task set mismatch")
    config = load_json(CONFIG_PATH)
    if report["run_config_id"] != config["run_config_id"]:
        raise ValueError("development run config ID mismatch")
    return {"manifest": manifest, "report": report, "records": records}


def analyze_run(run_dir: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(
            f"output directory already exists: {output_dir}"
        )
    package = verify_run_package(run_dir)
    gate = load_json(ADVANCEMENT_GATE_PATH)
    metrics = compute_gate_metrics(
        package["records"],
        package["report"],
    )
    evaluation = evaluate_gate(metrics, gate)
    output_dir.mkdir(parents=True)
    metric_path = output_dir / "development_gate_metrics.json"
    metric_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    evaluation_path = output_dir / "development_gate_evaluation.json"
    evaluation_path.write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    gate_snapshot = output_dir / "advancement_gate_snapshot.json"
    shutil.copyfile(ADVANCEMENT_GATE_PATH, gate_snapshot)
    artifacts = [metric_path, evaluation_path, gate_snapshot]
    manifest = {
        "schema_version": "1.0-development",
        "gate_id": gate["gate_id"],
        "source_bindings": {
            "run_manifest_sha256": file_hash(
                run_dir / "artifact_manifest.json"
            ),
            "advancement_gate_sha256": file_hash(
                ADVANCEMENT_GATE_PATH
            ),
            "hybrid_policy_sha256": file_hash(HYBRID_POLICY_PATH),
            "analyzer_sha256": file_hash(Path(__file__)),
        },
        "artifacts": [
            {"filename": path.name, "sha256": file_hash(path)}
            for path in artifacts
        ],
        "decision": evaluation["decision"],
        "validation_execution_authorized": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    (output_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return evaluation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    evaluation = analyze_run(
        args.run_dir.resolve(),
        args.output_dir.resolve(),
    )
    print(json.dumps(evaluation, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
