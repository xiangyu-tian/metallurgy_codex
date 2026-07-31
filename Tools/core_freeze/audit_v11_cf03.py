"""Build the v1.1 CF-03 candidate evidence package.

CF-03 accepts the reproducibility of the E1b pilot and its anti-leakage split.
It deliberately does not freeze the formal repeat count or promote pilot
results to confirmatory evidence; those decisions belong to CF-08/CF-09.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BENEFIT_RUN_DIR = PROJECT_ROOT / "outputs" / "e1b_v2_benefit_r3_20260730"
BENEFIT_ANALYSIS_DIR = (
    PROJECT_ROOT / "outputs" / "e1b_v2_benefit_analysis_r3_20260730"
)
GATE_RUN_DIR = PROJECT_ROOT / "outputs" / "e1b_v2_gate_r3_20260730"
GATE_ANALYSIS_DIR = (
    PROJECT_ROOT / "outputs" / "e1b_v2_gate_analysis_r3_20260730"
)
E1C_DEVELOPMENT_DIR = (
    PROJECT_ROOT / "outputs" / "e1c_development_full_r1_20260731"
)
E1C_EVALUATION_DIR = (
    PROJECT_ROOT / "outputs" / "e1c_evaluation_r1_20260731"
)
CONTRACTS_PATH = HERE / "verified_core" / "contracts_v1.json"

REQUIRED_CONDITIONS = {
    "no_tool",
    "forced_verified_oracle_parameters",
}
PILOT_REPEATS = {1, 2, 3}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def check(check_id: str, passed: bool, evidence: Any) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "passed": bool(passed),
        "evidence": evidence,
    }


def _safe_artifact(base_dir: Path, name: str) -> Path:
    candidate = Path(name)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"unsafe manifest path: {name}")
    artifact = (base_dir / candidate).resolve()
    artifact.relative_to(base_dir.resolve())
    return artifact


def verify_manifest(manifest_path: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    manifest = load_json(manifest_path)
    for row in manifest.get("artifacts", []):
        name = row.get("filename")
        if not isinstance(name, str):
            errors.append("manifest filename is not a string")
            continue
        try:
            artifact = _safe_artifact(manifest_path.parent, name)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not artifact.is_file():
            errors.append(f"missing manifest artifact: {name}")
        elif file_hash(artifact) != row.get("sha256"):
            errors.append(f"manifest hash mismatch: {name}")
    return not errors, errors


def _records_by_pair(
    records: Iterable[dict[str, Any]],
) -> dict[tuple[str, int], Counter[str]]:
    units: dict[tuple[str, int], Counter[str]] = {}
    for row in records:
        key = (row["task_id"], int(row["model_run_repeat"]))
        units.setdefault(key, Counter())[row["condition"]] += 1
    return units


def audit_e1b_run(
    run_dir: Path,
    expected_split: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    task_path = run_dir / "task_source_snapshot.json"
    report_path = run_dir / "run_report.json"
    records_path = run_dir / "run_records.jsonl"
    manifest_path = run_dir / "artifact_manifest.json"
    task_source = load_json(task_path)
    report = load_json(report_path)
    records = load_jsonl(records_path)
    tasks = task_source["tasks"]
    task_ids = {row["task_id"] for row in tasks}
    task_pair_ids = {row["task_pair_id"] for row in tasks}
    group_ids = {row["base_task_group_id"] for row in tasks}
    tool_ids = {row["source_tool_id"] for row in tasks}
    repeats = {int(row["model_run_repeat"]) for row in records}
    conditions = {row["condition"] for row in records}
    paired_units = _records_by_pair(records)
    manifest_ok, manifest_errors = verify_manifest(manifest_path)
    expected_pair_counter = Counter({condition: 1 for condition in REQUIRED_CONDITIONS})
    checks = [
        check(
            f"{expected_split}-MANIFEST",
            manifest_ok,
            "manifest verified" if manifest_ok else manifest_errors,
        ),
        check(
            f"{expected_split}-TASK-SOURCE-BINDING",
            report.get("task_source_sha256") == file_hash(task_path),
            {
                "reported": report.get("task_source_sha256"),
                "actual": file_hash(task_path),
            },
        ),
        check(
            f"{expected_split}-SPLIT",
            task_source.get("required_split") == expected_split
            and {row.get("split") for row in tasks} == {expected_split}
            and {row.get("split") for row in records} == {expected_split},
            {
                "required_split": task_source.get("required_split"),
                "task_splits": sorted({row.get("split") for row in tasks}),
                "record_splits": sorted({row.get("split") for row in records}),
            },
        ),
        check(
            f"{expected_split}-INDEPENDENT-REFERENCE",
            all(
                row.get("data_layer") == "controlled_executable_truth"
                and row.get("source_type") == "independent_contract_generator"
                and row.get("reference_execution", {}).get(
                    "production_code_imported"
                )
                is False
                for row in tasks
            ),
            f"task_count={len(tasks)}",
        ),
        check(
            f"{expected_split}-CONDITIONS",
            conditions == REQUIRED_CONDITIONS,
            sorted(conditions),
        ),
        check(
            f"{expected_split}-PILOT-REPEATS",
            repeats == PILOT_REPEATS,
            sorted(repeats),
        ),
        check(
            f"{expected_split}-PAIR-COMPLETENESS",
            len(paired_units) == len(tasks) * len(PILOT_REPEATS)
            and all(value == expected_pair_counter for value in paired_units.values()),
            {
                "observed_pair_units": len(paired_units),
                "expected_pair_units": len(tasks) * len(PILOT_REPEATS),
            },
        ),
        check(
            f"{expected_split}-RUN-STATUS",
            report.get("summary", {}).get("status") == "completed"
            and report.get("summary", {}).get("incomplete_pair_count") == 0
            and all(row.get("status") == "completed" for row in records),
            {
                "run_status": report.get("summary", {}).get("status"),
                "incomplete_pair_count": report.get("summary", {}).get(
                    "incomplete_pair_count"
                ),
            },
        ),
        check(
            f"{expected_split}-DEVELOPMENT-BOUNDARY",
            report.get("formal_repeats_frozen") is False
            and report.get("summary", {}).get("confirmatory_inference_allowed")
            is False
            and task_source.get("confirmatory_inference_allowed") is False
            and report.get("core_frozen") is False,
            {
                "formal_repeats_frozen": report.get("formal_repeats_frozen"),
                "confirmatory_inference_allowed": report.get("summary", {}).get(
                    "confirmatory_inference_allowed"
                ),
                "core_frozen": report.get("core_frozen"),
            },
        ),
    ]
    result = {
        "split": expected_split,
        "status": "passed" if all(row["passed"] for row in checks) else "failed",
        "run_id": report["run_id"],
        "dataset_id": report["dataset_id"],
        "task_count": len(tasks),
        "base_task_group_count": len(group_ids),
        "tool_ids": sorted(tool_ids),
        "model_run_repeats": sorted(repeats),
        "paired_repeat_count": len(paired_units),
        "record_count": len(records),
        "checks": checks,
    }
    details = {
        "task_ids": task_ids,
        "task_pair_ids": task_pair_ids,
        "base_task_group_ids": group_ids,
        "tool_ids": tool_ids,
        "task_source": task_source,
        "report": report,
        "records": records,
    }
    return result, details


def audit_analysis_artifacts() -> dict[str, Any]:
    benefit_report = load_json(
        BENEFIT_ANALYSIS_DIR / "benefit_analysis_report.json"
    )
    gate_report = load_json(GATE_ANALYSIS_DIR / "gate_policy_report.json")
    benefit_manifest_ok, benefit_errors = verify_manifest(
        BENEFIT_ANALYSIS_DIR / "artifact_manifest.json"
    )
    gate_manifest_ok, gate_errors = verify_manifest(
        GATE_ANALYSIS_DIR / "artifact_manifest.json"
    )
    gate_source = load_json(GATE_RUN_DIR / "task_source_snapshot.json")
    checks = [
        check(
            "CF03-BENEFIT-ANALYSIS-MANIFEST",
            benefit_manifest_ok,
            "manifest verified" if benefit_manifest_ok else benefit_errors,
        ),
        check(
            "CF03-GATE-ANALYSIS-MANIFEST",
            gate_manifest_ok,
            "manifest verified" if gate_manifest_ok else gate_errors,
        ),
        check(
            "CF03-BENEFIT-DESCRIPTIVE-ONLY",
            benefit_report.get("analysis_status")
            == "descriptive_development_only"
            and benefit_report.get("confirmatory_inference_allowed") is False
            and benefit_report.get("core_frozen") is False,
            {
                "analysis_status": benefit_report.get("analysis_status"),
                "confirmatory_inference_allowed": benefit_report.get(
                    "confirmatory_inference_allowed"
                ),
            },
        ),
        check(
            "CF03-GATE-INDEPENDENT-EVALUATION",
            gate_report.get("analysis_status")
            == "independent_gate_evaluation_completed"
            and gate_report.get("source_run_id")
            == load_json(GATE_RUN_DIR / "run_report.json").get("run_id")
            and gate_report.get("core_frozen") is False,
            {
                "analysis_status": gate_report.get("analysis_status"),
                "source_run_id": gate_report.get("source_run_id"),
            },
        ),
        check(
            "CF03-GATE-POLICY-FROZEN",
            gate_source.get("policy_revision_allowed") is False
            and gate_report.get("frozen_policy_sha256")
            == gate_source.get("frozen_policy_sha256")
            and gate_report.get("frozen_policy_git_commit")
            == gate_source.get("frozen_policy_git_commit"),
            {
                "policy_sha256": gate_source.get("frozen_policy_sha256"),
                "policy_git_commit": gate_source.get(
                    "frozen_policy_git_commit"
                ),
                "policy_revision_allowed": gate_source.get(
                    "policy_revision_allowed"
                ),
            },
        ),
    ]
    return {
        "status": "passed" if all(row["passed"] for row in checks) else "failed",
        "checks": checks,
        "benefit_report": benefit_report,
        "gate_report": gate_report,
    }


def audit_verified_tools(tool_ids: set[str]) -> dict[str, Any]:
    contracts = load_json(CONTRACTS_PATH)["contracts"]
    verified_ids = {
        row["tool_id"]
        for row in contracts
        if row.get("tool_status") == "verified_core"
    }
    passed = tool_ids <= verified_ids
    return {
        "status": "passed" if passed else "failed",
        "checks": [
            check(
                "CF03-VERIFIED-CORE-TOOLS",
                passed,
                {
                    "observed_tool_ids": sorted(tool_ids),
                    "verified_core_tool_ids": sorted(verified_ids),
                },
            )
        ],
    }


def audit_split_isolation(
    benefit: dict[str, Any],
    gate: dict[str, Any],
) -> dict[str, Any]:
    overlaps = {
        "task_id": sorted(benefit["task_ids"] & gate["task_ids"]),
        "task_pair_id": sorted(
            benefit["task_pair_ids"] & gate["task_pair_ids"]
        ),
        "base_task_group_id": sorted(
            benefit["base_task_group_ids"] & gate["base_task_group_ids"]
        ),
    }
    passed = all(not values for values in overlaps.values())
    return {
        "status": "passed" if passed else "failed",
        "checks": [
            check(
                "CF03-BENEFIT-GATE-ISOLATION",
                passed,
                overlaps,
            ),
            check(
                "CF03-FAMILY-LEVEL-TRANSFER-ONLY",
                benefit["tool_ids"] == gate["tool_ids"],
                {
                    "benefit_tool_ids": sorted(benefit["tool_ids"]),
                    "gate_tool_ids": sorted(gate["tool_ids"]),
                    "interpretation": (
                        "The same verified tool families are allowed across "
                        "splits; task, pair and base-group identities are not."
                    ),
                },
            ),
        ],
        "overlaps": overlaps,
    }


def _secondary_registry_entry(
    evidence_dir: Path,
    role: str,
) -> dict[str, Any]:
    report = load_json(evidence_dir / "run_report.json")
    task_source = load_json(evidence_dir / "task_source_snapshot.json")
    manifest_ok, manifest_errors = verify_manifest(
        evidence_dir / "artifact_manifest.json"
    )
    return {
        "evidence_role": role,
        "experiment": "E1c",
        "run_id": report["run_id"],
        "dataset_id": report["dataset_id"],
        "split": task_source["required_split"],
        "task_count": task_source["task_count"],
        "condition_count": report["summary"]["condition_count"],
        "model_run_repeats": 1,
        "manifest_verified": manifest_ok,
        "manifest_errors": manifest_errors,
        "eligible_for_e1b_primary_benefit_estimate": False,
        "eligible_for_formal_repeat_freeze": False,
        "confirmatory_inference_allowed": False,
        "purpose": (
            "Secondary mechanism evidence only; it must not be pooled with "
            "the E1b primary benefit contrast."
        ),
    }


def build_registry(
    benefit_result: dict[str, Any],
    gate_result: dict[str, Any],
    analyses: dict[str, Any],
) -> dict[str, Any]:
    benefit_report = analyses["benefit_report"]
    gate_report = analyses["gate_report"]
    return {
        "schema_version": "1.0",
        "registry_id": "V11-CF03-BENEFIT-EVIDENCE-20260731",
        "primary_estimand": (
            "Accuracy(Forced Verified Tool + Oracle Parameters) - "
            "Accuracy(No Tool)"
        ),
        "datasets": [
            {
                "evidence_role": "benefit_calibration",
                "experiment": "E1b",
                "run_id": benefit_result["run_id"],
                "dataset_id": benefit_result["dataset_id"],
                "split": benefit_result["split"],
                "task_count": benefit_result["task_count"],
                "base_task_group_count": benefit_result[
                    "base_task_group_count"
                ],
                "model_run_repeats": benefit_result["model_run_repeats"],
                "paired_repeat_count": benefit_result["paired_repeat_count"],
                "accuracy_gain": benefit_report["paired_accuracy_gain"],
                "eligible_for_pilot_effect_estimation": True,
                "eligible_for_gate_performance_claim": False,
                "confirmatory_inference_allowed": False,
            },
            {
                "evidence_role": "gate_evaluation",
                "experiment": "E1b",
                "run_id": gate_result["run_id"],
                "dataset_id": gate_result["dataset_id"],
                "split": gate_result["split"],
                "task_count": gate_result["task_count"],
                "base_task_group_count": gate_result[
                    "base_task_group_count"
                ],
                "model_run_repeats": gate_result["model_run_repeats"],
                "paired_repeat_count": gate_result["paired_repeat_count"],
                "candidate_policy_accuracy": gate_report[
                    "candidate_policy_accuracy"
                ],
                "eligible_for_pilot_effect_estimation": False,
                "eligible_for_gate_performance_claim": True,
                "confirmatory_inference_allowed": False,
            },
            _secondary_registry_entry(
                E1C_DEVELOPMENT_DIR,
                "mechanism_development_secondary",
            ),
            _secondary_registry_entry(
                E1C_EVALUATION_DIR,
                "mechanism_evaluation_secondary",
            ),
        ],
        "anti_leakage_policy": {
            "same_run_may_generate_benefit_and_prove_gate": False,
            "e1c_pooled_into_e1b_primary_estimand": False,
            "pilot_result_written_back_to_base_truth": False,
            "ai_silver_promoted_to_gold": False,
        },
        "formal_repeat_count_frozen": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }


def build_power_input(analyses: dict[str, Any]) -> dict[str, Any]:
    benefit = analyses["benefit_report"]
    gate = analyses["gate_report"]
    return {
        "schema_version": "1.0",
        "power_input_id": "V11-CF03-POWER-INPUT-20260731",
        "status": "pilot_descriptive_input_only",
        "primary_estimand": (
            "Accuracy(Forced Verified Tool + Oracle Parameters) - "
            "Accuracy(No Tool)"
        ),
        "benefit_calibration": {
            "task_count": benefit["task_count"],
            "base_task_group_count": benefit["base_task_group_count"],
            "paired_repeat_count": benefit["paired_cell_count"],
            "pilot_repeat_count": 3,
            "no_tool_accuracy": benefit["no_tool_accuracy"],
            "forced_accuracy": benefit["forced_accuracy"],
            "paired_accuracy_gain": benefit["paired_accuracy_gain"],
            "discordant_forced_better_count": benefit["positive_pair_count"],
            "discordant_no_tool_better_count": benefit[
                "negative_pair_count"
            ],
            "concordant_count": benefit["zero_pair_count"],
            "cluster_bootstrap": benefit["cluster_bootstrap"],
            "tool_family_effects": benefit["tool_effects"],
            "precision_policy_effects": benefit["precision_policy_effects"],
        },
        "gate_evaluation": {
            "task_count": gate["task_count"],
            "base_task_group_count": gate["base_task_group_count"],
            "paired_repeat_count": gate["paired_repeat_cell_count"],
            "pilot_repeat_count": 3,
            "no_tool_accuracy": gate["no_tool_accuracy"],
            "forced_accuracy": gate["forced_accuracy"],
            "candidate_policy_accuracy": gate["candidate_policy_accuracy"],
            "candidate_policy_call_rate": gate[
                "candidate_policy_call_rate"
            ],
            "positive_gain_cell_count": gate["positive_gain_cell_count"],
            "captured_positive_gain_cell_count": gate[
                "captured_positive_gain_cell_count"
            ],
        },
        "analysis_constraints": {
            "independence_unit_is_not_paired_repeat": True,
            "cluster_unit": "base_task_group_id",
            "task_family_and_tool_family_variation_required": True,
            "formal_repeat_count_frozen": False,
            "formal_sample_size_frozen": False,
            "may_be_used_for_confirmatory_inference": False,
            "next_gate": "CF-08 power analysis and repeat-count decision",
        },
        "core_frozen": False,
    }


def run_audit(output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")

    benefit_result, benefit_details = audit_e1b_run(
        BENEFIT_RUN_DIR,
        "benefit_estimation",
    )
    gate_result, gate_details = audit_e1b_run(
        GATE_RUN_DIR,
        "gate_evaluation",
    )
    analyses = audit_analysis_artifacts()
    isolation = audit_split_isolation(benefit_details, gate_details)
    verified_tools = audit_verified_tools(
        benefit_details["tool_ids"] | gate_details["tool_ids"]
    )
    completed_components = {
        "benefit_run_reproducibility": benefit_result["status"],
        "gate_run_reproducibility": gate_result["status"],
        "analysis_artifact_integrity": analyses["status"],
        "benefit_gate_split_isolation": isolation["status"],
        "verified_core_scope": verified_tools["status"],
    }
    evidence_ready = all(
        value == "passed" for value in completed_components.values()
    )
    report = {
        "schema_version": "1.0",
        "audit_id": "V11-CF03-CANDIDATE-AUDIT-20260731",
        "check_id": "CF-03",
        "status": "in_progress" if evidence_ready else "failed",
        "candidate_evidence_status": (
            "passed" if evidence_ready else "failed"
        ),
        "completed_components": completed_components,
        "benefit_run": benefit_result,
        "gate_run": gate_result,
        "analysis_audit": {
            "status": analyses["status"],
            "checks": analyses["checks"],
        },
        "split_isolation": isolation,
        "verified_tool_audit": verified_tools,
        "pending_requirements": [
            "CF-08 power analysis approval",
            "formal model-run repeat count freeze",
            "CF-09 sample-size addendum approval",
        ],
        "interpretation": (
            "E1b pilot tasks, independent references, paired controls, "
            "three-repeat pilot and anti-leakage split are reproducible. "
            "CF-03 remains in_progress until CF-08/CF-09 freeze the formal "
            "repeat count and sample-size basis."
        ),
        "pilot_results_promoted_to_confirmatory": False,
        "tool_benefit_written_back_to_base_truth": False,
        "core_frozen": False,
    }
    registry = build_registry(benefit_result, gate_result, analyses)
    power_input = build_power_input(analyses)

    output_dir.mkdir(parents=True)
    artifact_payloads = {
        "cf03_audit_report.json": report,
        "benefit_evidence_registry.json": registry,
        "power_input.json": power_input,
    }
    for filename, payload in artifact_payloads.items():
        (output_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    source_paths = [
        BENEFIT_RUN_DIR / "task_source_snapshot.json",
        BENEFIT_RUN_DIR / "run_records.jsonl",
        BENEFIT_RUN_DIR / "run_report.json",
        BENEFIT_RUN_DIR / "artifact_manifest.json",
        BENEFIT_ANALYSIS_DIR / "benefit_analysis_report.json",
        BENEFIT_ANALYSIS_DIR / "artifact_manifest.json",
        GATE_RUN_DIR / "task_source_snapshot.json",
        GATE_RUN_DIR / "run_records.jsonl",
        GATE_RUN_DIR / "run_report.json",
        GATE_RUN_DIR / "artifact_manifest.json",
        GATE_ANALYSIS_DIR / "gate_policy_report.json",
        GATE_ANALYSIS_DIR / "artifact_manifest.json",
        E1C_DEVELOPMENT_DIR / "run_report.json",
        E1C_DEVELOPMENT_DIR / "artifact_manifest.json",
        E1C_EVALUATION_DIR / "run_report.json",
        E1C_EVALUATION_DIR / "artifact_manifest.json",
        CONTRACTS_PATH,
        Path(__file__),
    ]
    manifest = {
        "schema_version": "1.0",
        "audit_id": report["audit_id"],
        "artifacts": [
            {
                "filename": filename,
                "sha256": file_hash(output_dir / filename),
            }
            for filename in artifact_payloads
        ],
        "source_artifacts": [
            {"filename": relative(path), "sha256": file_hash(path)}
            for path in source_paths
        ],
        "cf03_status": report["status"],
        "core_frozen": False,
    }
    (output_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "v11_cf03_candidate_20260731",
    )
    args = parser.parse_args()
    report = run_audit(args.output_dir)
    print(
        json.dumps(
            {
                "audit_id": report["audit_id"],
                "cf03_status": report["status"],
                "candidate_evidence_status": report[
                    "candidate_evidence_status"
                ],
                "pending_requirements": report["pending_requirements"],
                "core_frozen": report["core_frozen"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["candidate_evidence_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
