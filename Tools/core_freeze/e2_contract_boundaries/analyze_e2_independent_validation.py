"""Analyze the locked E2 independent-validation comparison descriptively."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from core_freeze.e2_contract_boundaries.run_e2_development import (
    file_hash,
    load_json,
)
from core_freeze.e2_contract_boundaries.run_e2_independent_validation import (
    BASE_POLICY_PATH,
    CONDITION_ORDER,
)


def _predicted_flags(record: dict[str, Any]) -> list[str]:
    if record["condition"] == "flags_only_v1_1":
        return record.get("predicted_flags") or []
    return record.get("merged_flags") or []


def _flags_exact(record: dict[str, Any]) -> bool:
    if record["condition"] == "flags_only_v1_1":
        return bool(record.get("flags_exact"))
    return bool(record.get("merged_flags_exact"))


def wilson_interval(successes: int, total: int) -> list[float]:
    if total <= 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total
            + z * z / (4 * total * total)
        )
        / denominator
    )
    return [center - margin, center + margin]


def _condition_metrics(
    records: list[dict[str, Any]],
    condition_id: str,
    flag_order: list[str],
    gold_supported_flags: list[str],
) -> dict[str, Any]:
    subset = [row for row in records if row["condition"] == condition_id]
    per_flag: dict[str, dict[str, float | int]] = {}
    total_tp = total_fp = total_fn = 0
    for flag in flag_order:
        tp = fp = fn = 0
        for row in subset:
            expected = set(row["expected_flags"])
            predicted = set(_predicted_flags(row))
            tp += int(flag in expected and flag in predicted)
            fp += int(flag not in expected and flag in predicted)
            fn += int(flag in expected and flag not in predicted)
        denominator = 2 * tp + fp + fn
        f1 = 2 * tp / denominator if denominator else 1.0
        per_flag[flag] = {
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "f1": f1,
        }
        total_tp += tp
        total_fp += fp
        total_fn += fn
    micro_denominator = 2 * total_tp + total_fp + total_fn
    exact_count = sum(_flags_exact(row) for row in subset)
    action_count = sum(bool(row.get("action_correct")) for row in subset)
    return {
        "condition_id": condition_id,
        "cell_count": len(subset),
        "completed_count": sum(row["status"] == "completed" for row in subset),
        "provider_failure_count": sum(
            row["status"] != "completed" for row in subset
        ),
        "flags_exact_count": exact_count,
        "flags_exact_accuracy": exact_count / len(subset),
        "flags_exact_wilson_95": wilson_interval(exact_count, len(subset)),
        "action_correct_count": action_count,
        "action_accuracy": action_count / len(subset),
        "action_wilson_95": wilson_interval(action_count, len(subset)),
        "premature_call_count": sum(
            row["expected_action"] != "call"
            and row.get("predicted_action") == "call"
            for row in subset
        ),
        "all_flag_micro_f1": (
            2 * total_tp / micro_denominator if micro_denominator else 1.0
        ),
        "gold_supported_flag_macro_f1": sum(
            float(per_flag[flag]["f1"]) for flag in gold_supported_flags
        )
        / len(gold_supported_flags),
        "fixed_flag_macro_f1": sum(
            float(per_flag[flag]["f1"]) for flag in flag_order
        )
        / len(flag_order),
        "gold_supported_flags": gold_supported_flags,
        "flag_metrics": per_flag,
    }


def analyze_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    if len(records) != 80:
        raise ValueError("independent validation must contain 80 records")
    cell_ids = [row["cell_id"] for row in records]
    if len(set(cell_ids)) != len(cell_ids):
        raise ValueError("duplicate validation cell ID")
    task_ids = sorted({row["task_id"] for row in records})
    if len(task_ids) != 40:
        raise ValueError("independent validation must contain 40 tasks")
    by_key = {(row["task_id"], row["condition"]): row for row in records}
    expected_keys = {
        (task_id, condition)
        for task_id in task_ids
        for condition in CONDITION_ORDER
    }
    if set(by_key) != expected_keys:
        raise ValueError("validation pairing is incomplete")
    policy = load_json(BASE_POLICY_PATH)
    flag_order = list(policy["flags"])
    gold_supported_flags = [
        flag
        for flag in flag_order
        if any(flag in row["expected_flags"] for row in records)
    ]
    condition_metrics = {
        condition: _condition_metrics(
            records,
            condition,
            flag_order,
            gold_supported_flags,
        )
        for condition in CONDITION_ORDER
    }
    paired_rows = []
    for task_id in task_ids:
        baseline = by_key[(task_id, "flags_only_v1_1")]
        hybrid = by_key[(task_id, "hybrid_semantic_v1_4")]
        paired_rows.append(
            {
                "task_id": task_id,
                "expected_flags": baseline["expected_flags"],
                "expected_action": baseline["expected_action"],
                "baseline_predicted_flags": _predicted_flags(baseline),
                "hybrid_predicted_flags": _predicted_flags(hybrid),
                "baseline_flags_exact": _flags_exact(baseline),
                "hybrid_flags_exact": _flags_exact(hybrid),
                "baseline_action_correct": bool(baseline["action_correct"]),
                "hybrid_action_correct": bool(hybrid["action_correct"]),
            }
        )
    paired_summary = {
        "flags_baseline_wrong_hybrid_correct": sum(
            not row["baseline_flags_exact"] and row["hybrid_flags_exact"]
            for row in paired_rows
        ),
        "flags_baseline_correct_hybrid_wrong": sum(
            row["baseline_flags_exact"] and not row["hybrid_flags_exact"]
            for row in paired_rows
        ),
        "flags_net_hybrid_advantage": sum(
            int(row["hybrid_flags_exact"])
            - int(row["baseline_flags_exact"])
            for row in paired_rows
        ),
        "action_baseline_wrong_hybrid_correct": sum(
            not row["baseline_action_correct"]
            and row["hybrid_action_correct"]
            for row in paired_rows
        ),
        "action_baseline_correct_hybrid_wrong": sum(
            row["baseline_action_correct"]
            and not row["hybrid_action_correct"]
            for row in paired_rows
        ),
        "action_net_hybrid_advantage": sum(
            int(row["hybrid_action_correct"])
            - int(row["baseline_action_correct"])
            for row in paired_rows
        ),
    }
    return {
        "condition_metrics": condition_metrics,
        "paired_summary": paired_summary,
        "paired_rows": paired_rows,
        "interpretation_limits": {
            "same_five_tool_families": True,
            "model_run_repeats": 1,
            "confirmatory_inference_allowed": False,
            "post_validation_policy_revision_allowed": False,
        },
    }


def write_analysis(run_dir: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    records_path = run_dir / "run_records.jsonl"
    run_report_path = run_dir / "run_report.json"
    run_manifest_path = run_dir / "artifact_manifest.json"
    records = [
        json.loads(line)
        for line in records_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    result = analyze_records(records)
    run_report = load_json(run_report_path)
    output_dir.mkdir(parents=True)
    metrics_path = output_dir / "condition_metrics.json"
    metrics_path.write_text(
        json.dumps(result["condition_metrics"], ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    paired_path = output_dir / "paired_task_results.jsonl"
    paired_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in result["paired_rows"]
        ),
        encoding="utf-8",
    )
    report = {
        "schema_version": "1.0",
        "analysis_id": "E2-INDEPENDENT-VALIDATION-ANALYSIS-V1-20260803",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_report["run_id"],
        "dataset_id": run_report["dataset_id"],
        "status": "completed",
        "paired_summary": result["paired_summary"],
        "interpretation_limits": result["interpretation_limits"],
        "model_performance_claim_allowed": True,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    report_path = output_dir / "analysis_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    artifacts = [metrics_path, paired_path, report_path]
    manifest = {
        "schema_version": "1.0",
        "analysis_id": report["analysis_id"],
        "source_bindings": {
            "run_records_sha256": file_hash(records_path),
            "run_report_sha256": file_hash(run_report_path),
            "run_manifest_sha256": file_hash(run_manifest_path),
            "analyzer_sha256": file_hash(Path(__file__)),
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
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = write_analysis(args.run_dir.resolve(), args.output_dir.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
