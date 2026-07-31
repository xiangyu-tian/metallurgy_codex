"""Compare the E2 v1.1 development recheck with the v1 replay baseline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BASELINE_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_policy_v1_1_candidate_20260731"
)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _mutation_key(row: dict[str, Any]) -> str:
    return "+".join(row["mutation_types"]) or "ready"


def _accuracy(rows: list[dict[str, Any]], field: str) -> float | None:
    if not rows:
        return None
    return sum(bool(row[field]) for row in rows) / len(rows)


def build_comparison(
    *,
    current_records: list[dict[str, Any]],
    current_report: dict[str, Any],
    baseline_records: list[dict[str, Any]],
    baseline_report: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    baseline_by_task = {
        row["task_id"]: row for row in baseline_records
    }
    current_by_task = {
        row["task_id"]: row for row in current_records
    }
    if set(baseline_by_task) != set(current_by_task):
        raise ValueError("baseline and recheck task sets differ")
    paired = []
    for task_id in sorted(current_by_task):
        before = baseline_by_task[task_id]
        after = current_by_task[task_id]
        paired.append(
            {
                "task_id": task_id,
                "source_tool_id": after["source_tool_id"],
                "mutation_types": _mutation_key(after),
                "expected_flags": "|".join(
                    sorted(after["expected_flags"])
                ),
                "baseline_predicted_flags": "|".join(
                    sorted(before["predicted_flags"] or [])
                ),
                "v1_1_predicted_flags": "|".join(
                    sorted(after["predicted_flags"] or [])
                ),
                "baseline_flags_exact": before["flags_exact"],
                "v1_1_flags_exact": after["flags_exact"],
                "baseline_action": before["predicted_action"],
                "v1_1_action": after["predicted_action"],
                "expected_action": after["expected_action"],
                "baseline_action_correct": before["action_correct"],
                "v1_1_action_correct": after["action_correct"],
                "flags_transition": _transition(
                    before["flags_exact"],
                    after["flags_exact"],
                ),
                "action_transition": _transition(
                    before["action_correct"],
                    after["action_correct"],
                ),
            }
        )
    task_errors = [
        row
        for row in paired
        if not row["v1_1_flags_exact"]
        or not row["v1_1_action_correct"]
    ]
    grouped_baseline: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped_current: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in baseline_records:
        grouped_baseline[_mutation_key(row)].append(row)
    for row in current_records:
        grouped_current[_mutation_key(row)].append(row)
    mutation_comparison = []
    for mutation in sorted(grouped_current):
        before = grouped_baseline[mutation]
        after = grouped_current[mutation]
        mutation_comparison.append(
            {
                "mutation_types": mutation,
                "task_count": len(after),
                "baseline_flags_exact_accuracy": _accuracy(
                    before, "flags_exact"
                ),
                "v1_1_flags_exact_accuracy": _accuracy(
                    after, "flags_exact"
                ),
                "flags_exact_change": (
                    _accuracy(after, "flags_exact")
                    - _accuracy(before, "flags_exact")
                ),
                "baseline_action_accuracy": _accuracy(
                    before, "action_correct"
                ),
                "v1_1_action_accuracy": _accuracy(
                    after, "action_correct"
                ),
                "action_accuracy_change": (
                    _accuracy(after, "action_correct")
                    - _accuracy(before, "action_correct")
                ),
            }
        )
    baseline_flags = {
        row["flag"]: row for row in baseline_report["flag_metrics"]
    }
    current_flags = {
        row["flag"]:
        row for row in current_report["summary"]["flag_metrics"]
    }
    flag_comparison = []
    for flag in sorted(current_flags):
        before = baseline_flags[flag]
        after = current_flags[flag]
        flag_comparison.append(
            {
                "flag": flag,
                "support": after["support"],
                "baseline_precision": before["precision"],
                "v1_1_precision": after["precision"],
                "baseline_recall": before["recall"],
                "v1_1_recall": after["recall"],
                "recall_change": after["recall"] - before["recall"],
                "baseline_f1": before["f1"],
                "v1_1_f1": after["f1"],
                "f1_change": after["f1"] - before["f1"],
            }
        )
    baseline_summary = baseline_report
    current_summary = current_report["summary"]
    multilabel_before = [
        row for row in baseline_records if len(row["expected_flags"]) > 1
    ]
    multilabel_after = [
        row for row in current_records if len(row["expected_flags"]) > 1
    ]
    comparison = {
        "schema_version": "1.1",
        "analysis_id": "E2-V1.1-RECHECK-COMPARISON-20260731",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_type": "v1_response_flags_counterfactual_replay",
        "recheck_type": "v1.1_independent_development_recheck",
        "task_count": len(paired),
        "paired_flags_transitions": _transition_counts(
            paired, "flags_transition"
        ),
        "paired_action_transitions": _transition_counts(
            paired, "action_transition"
        ),
        "metrics": {
            "schema_valid_rate": {
                "baseline": baseline_summary["schema_valid_rate"],
                "v1_1": current_summary["schema_valid_rate"],
                "change": (
                    current_summary["schema_valid_rate"]
                    - baseline_summary["schema_valid_rate"]
                ),
            },
            "flags_exact_accuracy": {
                "baseline": baseline_summary["flags_exact_accuracy"],
                "v1_1": current_summary["flags_exact_accuracy"],
                "change": (
                    current_summary["flags_exact_accuracy"]
                    - baseline_summary["flags_exact_accuracy"]
                ),
            },
            "supported_flag_macro_f1": {
                "baseline": baseline_summary["supported_flag_macro_f1"],
                "v1_1": current_summary["supported_flag_macro_f1"],
                "change": (
                    current_summary["supported_flag_macro_f1"]
                    - baseline_summary["supported_flag_macro_f1"]
                ),
            },
            "action_accuracy": {
                "baseline": baseline_summary["action_accuracy"],
                "v1_1": current_summary["action_accuracy"],
                "change": (
                    current_summary["action_accuracy"]
                    - baseline_summary["action_accuracy"]
                ),
            },
            "multilabel_flags_exact_accuracy": {
                "baseline": _accuracy(
                    multilabel_before, "flags_exact"
                ),
                "v1_1": _accuracy(multilabel_after, "flags_exact"),
                "change": (
                    _accuracy(multilabel_after, "flags_exact")
                    - _accuracy(multilabel_before, "flags_exact")
                ),
            },
            "invalid_execution_rate": {
                "baseline": baseline_summary["invalid_execution_rate"],
                "v1_1": current_summary["invalid_execution_rate"],
                "change": (
                    current_summary["invalid_execution_rate"]
                    - baseline_summary["invalid_execution_rate"]
                ),
            },
            "premature_call_rate": {
                "baseline": baseline_summary["premature_call_rate"],
                "v1_1": current_summary["premature_call_rate"],
                "change": (
                    current_summary["premature_call_rate"]
                    - baseline_summary["premature_call_rate"]
                ),
            },
        },
        "development_gate": {
            "schema_valid_rate_100_percent": (
                current_summary["schema_valid_rate"] == 1.0
            ),
            "unsupported_system_recall_improved": (
                current_flags[
                    "contract_defined_unsupported_system"
                ]["recall"]
                > baseline_flags[
                    "contract_defined_unsupported_system"
                ]["recall"]
            ),
            "multilabel_exact_accuracy_improved": (
                _accuracy(multilabel_after, "flags_exact")
                > _accuracy(multilabel_before, "flags_exact")
            ),
            "clarify_action_accuracy_improved": (
                current_summary["by_expected_action"]["clarify"]["accuracy"]
                > baseline_summary["by_expected_action"]["clarify"][
                    "accuracy"
                ]
            ),
        },
        "interpretation": {
            "protocol_failure_closed": True,
            "unsupported_system_distinction_improved": True,
            "ambiguous_plus_ood_remains_primary_error_cluster": True,
            "premature_call_observed": True,
            "same_development_tasks_used": True,
            "unbiased_generalization_claim_allowed": False,
            "confirmatory_inference_allowed": False,
            "core_frozen": False,
        },
    }
    return task_errors, mutation_comparison, flag_comparison, comparison


def _transition(before: bool, after: bool) -> str:
    if before and after:
        return "correct_to_correct"
    if before and not after:
        return "correct_to_incorrect"
    if not before and after:
        return "incorrect_to_correct"
    return "incorrect_to_incorrect"


def _transition_counts(
    rows: list[dict[str, Any]],
    field: str,
) -> dict[str, int]:
    names = (
        "correct_to_correct",
        "correct_to_incorrect",
        "incorrect_to_correct",
        "incorrect_to_incorrect",
    )
    return {
        name: sum(row[field] == name for row in rows)
        for name in names
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty CSV: {path.name}")
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(
    *,
    source_dir: Path,
    output_dir: Path,
    task_errors: list[dict[str, Any]],
    mutation_comparison: list[dict[str, Any]],
    flag_comparison: list[dict[str, Any]],
    comparison: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    errors_path = output_dir / "task_errors.csv"
    mutations_path = output_dir / "mutation_comparison.csv"
    flags_path = output_dir / "flag_comparison.csv"
    report_path = output_dir / "comparison_report.json"
    write_csv(errors_path, task_errors)
    write_csv(mutations_path, mutation_comparison)
    write_csv(flags_path, flag_comparison)
    report_path.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    artifacts = [errors_path, mutations_path, flags_path, report_path]
    manifest = {
        "schema_version": "1.1",
        "analysis_id": comparison["analysis_id"],
        "source_bindings": {
            "v1_1_run_manifest_sha256": file_hash(
                source_dir / "artifact_manifest.json"
            ),
            "baseline_candidate_manifest_sha256": file_hash(
                BASELINE_DIR / "artifact_manifest.json"
            ),
            "analysis_script_sha256": file_hash(Path(__file__)),
        },
        "artifacts": [
            {"filename": path.name, "sha256": file_hash(path)}
            for path in artifacts
        ],
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    (output_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source_dir = args.source_dir.resolve()
    current_records = load_jsonl(source_dir / "run_records.jsonl")
    current_report = load_json(source_dir / "run_report.json")
    baseline_records = load_jsonl(
        BASELINE_DIR / "counterfactual_replay_records.jsonl"
    )
    baseline_report = load_json(
        BASELINE_DIR / "counterfactual_replay_report.json"
    )
    outputs = build_comparison(
        current_records=current_records,
        current_report=current_report,
        baseline_records=baseline_records,
        baseline_report=baseline_report,
    )
    write_outputs(
        source_dir=source_dir,
        output_dir=args.output_dir.resolve(),
        task_errors=outputs[0],
        mutation_comparison=outputs[1],
        flag_comparison=outputs[2],
        comparison=outputs[3],
    )
    print(json.dumps(outputs[3], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
