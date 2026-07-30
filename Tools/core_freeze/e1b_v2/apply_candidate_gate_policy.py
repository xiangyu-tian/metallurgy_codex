"""Apply and audit the frozen pre-gate E1b candidate policy.

The policy consumes task metadata and derived numerical features only.  It never
uses task identifiers, problem text, expected answers, or evaluation outcomes
to make a decision.  Development outcomes are joined only after assignment to
produce a retrospective fit audit.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[2]

ALLOWED_ACTIONS = {"CALL_VERIFIED_TOOL", "ANSWER_WITHOUT_TOOL"}
ALLOWED_DIRECT_FIELDS = {"source_tool_id", "precision_policy"}
ALLOWED_DERIVED_FIELDS = {
    "composition_dynamic_range",
    "composition_requires_rescaling",
}
ALLOWED_OPS = {"eq", "gte"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def derive_features(task: dict[str, Any]) -> dict[str, Any]:
    compositions = task.get("canonical_inputs", {}).get("compositions")
    dynamic_range: float | None = None
    requires_rescaling: bool | None = None
    if isinstance(compositions, dict) and compositions:
        values = [float(value) for value in compositions.values()]
        nonzero = [abs(value) for value in values if value != 0]
        if nonzero:
            dynamic_range = max(nonzero) / min(nonzero)
        requires_rescaling = abs(sum(values) - 1.0) > 1e-12
    return {
        "source_tool_id": task.get("source_tool_id"),
        "precision_policy": task.get("precision_policy"),
        "composition_dynamic_range": dynamic_range,
        "composition_requires_rescaling": requires_rescaling,
    }


def validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("policy_status") != "candidate_frozen_pre_gate":
        raise ValueError("policy must be candidate_frozen_pre_gate")
    actions = set(policy.get("scope", {}).get("allowed_actions", []))
    if actions != ALLOWED_ACTIONS:
        raise ValueError(f"unexpected allowed actions: {sorted(actions)}")
    if policy.get("development_evidence", {}).get(
        "gate_evaluation_effects_observed"
    ):
        raise ValueError("pre-gate policy must not observe gate effects")
    constraints = policy.get("freeze_constraints", {})
    required_true = (
        "thresholds_are_not_optimized_on_gate",
        "gate_evaluation_may_not_modify_this_version",
        "post_gate_changes_require_new_policy_version",
        "development_fit_is_not_confirmatory_evidence",
    )
    if not all(constraints.get(key) is True for key in required_true):
        raise ValueError("policy freeze constraints are incomplete")

    priorities: list[int] = []
    rule_ids: set[str] = set()
    for rule in policy.get("rules", []):
        rule_id = rule.get("rule_id")
        if not rule_id or rule_id in rule_ids:
            raise ValueError("policy rule ids must be present and unique")
        rule_ids.add(rule_id)
        priorities.append(int(rule["priority"]))
        if rule.get("action") not in ALLOWED_ACTIONS:
            raise ValueError(f"invalid action in {rule_id}")
        predicates = rule.get("when", {}).get("all")
        if not isinstance(predicates, list) or not predicates:
            raise ValueError(f"{rule_id} must define a non-empty all predicate")
        for predicate in predicates:
            field = predicate.get("field")
            if field not in ALLOWED_DIRECT_FIELDS | ALLOWED_DERIVED_FIELDS:
                raise ValueError(f"forbidden or unknown policy field: {field}")
            if predicate.get("op") not in ALLOWED_OPS:
                raise ValueError(f"unsupported predicate op in {rule_id}")
    if len(priorities) != len(set(priorities)):
        raise ValueError("policy priorities must be unique")
    if policy.get("default_decision", {}).get("action") not in ALLOWED_ACTIONS:
        raise ValueError("invalid default action")


def predicate_matches(features: dict[str, Any], predicate: dict[str, Any]) -> bool:
    actual = features.get(predicate["field"])
    expected = predicate["value"]
    if predicate["op"] == "eq":
        return actual == expected
    if predicate["op"] == "gte":
        return actual is not None and float(actual) >= float(expected)
    raise ValueError(f"unsupported predicate op: {predicate['op']}")


def classify_task(
    task: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    features = derive_features(task)
    for rule in sorted(policy["rules"], key=lambda row: int(row["priority"])):
        if all(
            predicate_matches(features, predicate)
            for predicate in rule["when"]["all"]
        ):
            return {
                **features,
                "action": rule["action"],
                "rule_id": rule["rule_id"],
                "reason_code": rule["reason_code"],
            }
    default = policy["default_decision"]
    return {
        **features,
        "action": default["action"],
        "rule_id": "DEFAULT",
        "reason_code": default["reason_code"],
    }


def read_task_effects(path: Path) -> dict[str, dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    effects: dict[str, dict[str, Any]] = {}
    for row in rows:
        task_id = row["task_id"]
        if task_id in effects:
            raise ValueError(f"duplicate task effect: {task_id}")
        effects[task_id] = {
            **row,
            "no_tool_correct_repeats": int(row["no_tool_correct_repeats"]),
            "forced_correct_repeats": int(row["forced_correct_repeats"]),
            "repeat_count": int(row["repeat_count"]),
            "accuracy_gain": float(row["accuracy_gain"]),
        }
    return effects


def verify_development_sources(
    policy: dict[str, Any],
    tasks_path: Path,
    analysis_report_path: Path,
    effects_path: Path,
) -> None:
    evidence = policy["development_evidence"]
    expected = {
        tasks_path: evidence["benefit_tasks_sha256"],
        analysis_report_path: evidence["analysis_report_sha256"],
        effects_path: evidence["task_effects_sha256"],
    }
    for path, expected_hash in expected.items():
        actual_hash = file_hash(path)
        if actual_hash != expected_hash:
            raise ValueError(
                f"development source hash mismatch for {path}: "
                f"{actual_hash} != {expected_hash}"
            )


def audit_policy(
    policy_path: Path,
    tasks_path: Path,
    analysis_report_path: Path,
    effects_path: Path,
    output_dir: Path,
    expected_split: str = "benefit_estimation",
) -> dict[str, Any]:
    policy = load_json(policy_path)
    validate_policy(policy)
    verify_development_sources(
        policy,
        tasks_path,
        analysis_report_path,
        effects_path,
    )
    tasks_doc = load_json(tasks_path)
    analysis_report = load_json(analysis_report_path)
    tasks = tasks_doc["tasks"]
    if not tasks or any(task.get("split") != expected_split for task in tasks):
        raise ValueError(f"all tasks must use expected split {expected_split}")
    if expected_split != "benefit_estimation":
        raise ValueError("development fit audit accepts benefit_estimation only")
    if tasks_doc.get("dataset_id") != policy["development_evidence"]["dataset_id"]:
        raise ValueError("task dataset id does not match frozen policy evidence")
    if analysis_report.get("analysis_id") != policy["development_evidence"][
        "analysis_id"
    ]:
        raise ValueError("analysis id does not match frozen policy evidence")
    if analysis_report.get("gate_evaluation_opened") is not False:
        raise ValueError("development analysis must keep gate evaluation sealed")

    effects = read_task_effects(effects_path)
    task_ids = {task["task_id"] for task in tasks}
    if task_ids != set(effects):
        raise ValueError("task/effect id sets differ")

    assignments: list[dict[str, Any]] = []
    for task in tasks:
        decision = classify_task(task, policy)
        effect = effects[task["task_id"]]
        selected_correct = (
            effect["forced_correct_repeats"]
            if decision["action"] == "CALL_VERIFIED_TOOL"
            else effect["no_tool_correct_repeats"]
        )
        assignments.append(
            {
                "task_id": task["task_id"],
                "source_tool_id": task["source_tool_id"],
                "base_task_group_id": task["base_task_group_id"],
                "precision_policy": task["precision_policy"],
                "composition_dynamic_range": (
                    ""
                    if decision["composition_dynamic_range"] is None
                    else f"{decision['composition_dynamic_range']:.12g}"
                ),
                "composition_requires_rescaling": (
                    ""
                    if decision["composition_requires_rescaling"] is None
                    else str(
                        decision["composition_requires_rescaling"]
                    ).lower()
                ),
                "action": decision["action"],
                "rule_id": decision["rule_id"],
                "reason_code": decision["reason_code"],
                "repeat_count": effect["repeat_count"],
                "no_tool_correct_repeats": effect[
                    "no_tool_correct_repeats"
                ],
                "forced_correct_repeats": effect[
                    "forced_correct_repeats"
                ],
                "selected_correct_repeats": selected_correct,
                "observed_gain_repeats": (
                    effect["forced_correct_repeats"]
                    - effect["no_tool_correct_repeats"]
                ),
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    assignments_path = output_dir / "development_policy_assignments.csv"
    with assignments_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(assignments[0]))
        writer.writeheader()
        writer.writerows(assignments)

    total_cells = sum(row["repeat_count"] for row in assignments)
    no_tool_correct = sum(
        row["no_tool_correct_repeats"] for row in assignments
    )
    forced_correct = sum(
        row["forced_correct_repeats"] for row in assignments
    )
    selected_correct = sum(
        row["selected_correct_repeats"] for row in assignments
    )
    call_cells = sum(
        row["repeat_count"]
        for row in assignments
        if row["action"] == "CALL_VERIFIED_TOOL"
    )
    positive_gain_cells = sum(
        max(0, row["observed_gain_repeats"]) for row in assignments
    )
    captured_gain_cells = sum(
        max(0, row["observed_gain_repeats"])
        for row in assignments
        if row["action"] == "CALL_VERIFIED_TOOL"
    )

    report = {
        "schema_version": "1.0",
        "audit_id": "E1B-CANDIDATE-GATE-POLICY-V1-DEVELOPMENT-FIT",
        "policy_id": policy["policy_id"],
        "policy_version": policy["policy_version"],
        "policy_status": policy["policy_status"],
        "policy_sha256": file_hash(policy_path),
        "source_dataset_id": tasks_doc["dataset_id"],
        "source_analysis_id": analysis_report["analysis_id"],
        "task_count": len(assignments),
        "repeat_cell_count": total_cells,
        "action_task_counts": dict(
            sorted(Counter(row["action"] for row in assignments).items())
        ),
        "rule_task_counts": dict(
            sorted(Counter(row["rule_id"] for row in assignments).items())
        ),
        "call_cell_count": call_cells,
        "call_rate": call_cells / total_cells,
        "avoided_call_count_vs_always_forced": total_cells - call_cells,
        "always_no_tool_accuracy": no_tool_correct / total_cells,
        "always_forced_accuracy": forced_correct / total_cells,
        "candidate_policy_accuracy": selected_correct / total_cells,
        "candidate_gain_vs_always_no_tool": (
            selected_correct - no_tool_correct
        )
        / total_cells,
        "candidate_loss_vs_always_forced": (
            selected_correct - forced_correct
        )
        / total_cells,
        "positive_gain_cell_count": positive_gain_cells,
        "captured_positive_gain_cell_count": captured_gain_cells,
        "captured_positive_gain_fraction": (
            captured_gain_cells / positive_gain_cells
            if positive_gain_cells
            else math.nan
        ),
        "interpretation": {
            "analysis_type": "retrospective_development_fit",
            "confirmatory_inference_allowed": False,
            "gate_evaluation_opened": False,
            "policy_may_be_revised_from_this_fit": False,
            "next_allowed_step": "freeze_artifacts_then_open_gate_evaluation",
        },
        "core_frozen": False,
    }
    report_path = output_dir / "development_fit_report.json"
    write_json(report_path, report)

    policy_snapshot_path = output_dir / policy_path.name
    policy_snapshot_path.write_bytes(policy_path.read_bytes())
    source_snapshot_path = output_dir / "policy_evaluator_source_snapshot.py"
    source_snapshot_path.write_bytes(Path(__file__).read_bytes())

    manifest_path = output_dir / "artifact_manifest.json"
    artifacts = [
        policy_snapshot_path,
        source_snapshot_path,
        assignments_path,
        report_path,
    ]
    manifest = {
        "schema_version": "1.0",
        "policy_id": policy["policy_id"],
        "policy_status": policy["policy_status"],
        "artifacts": [
            {"filename": path.name, "sha256": file_hash(path)}
            for path in artifacts
        ],
        "development_source_hashes": {
            "benefit_tasks": file_hash(tasks_path),
            "analysis_report": file_hash(analysis_report_path),
            "task_effects": file_hash(effects_path),
        },
        "gate_evaluation_opened": False,
        "core_frozen": False,
    }
    write_json(manifest_path, manifest)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--policy",
        type=Path,
        default=HERE / "candidate_gate_policy_v1.json",
    )
    parser.add_argument(
        "--tasks",
        type=Path,
        default=(
            PROJECT_ROOT
            / "outputs"
            / "e1b_benefit_taskset_v2_20260730"
            / "e1b_benefit_tasks_v2.json"
        ),
    )
    parser.add_argument(
        "--analysis-report",
        type=Path,
        default=(
            PROJECT_ROOT
            / "outputs"
            / "e1b_v2_benefit_analysis_r3_20260730"
            / "benefit_analysis_report.json"
        ),
    )
    parser.add_argument(
        "--task-effects",
        type=Path,
        default=(
            PROJECT_ROOT
            / "outputs"
            / "e1b_v2_benefit_analysis_r3_20260730"
            / "task_effects.csv"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=(
            PROJECT_ROOT
            / "outputs"
            / "e1b_v2_candidate_gate_policy_v1_20260730"
        ),
    )
    args = parser.parse_args()
    report = audit_policy(
        args.policy,
        args.tasks,
        args.analysis_report,
        args.task_effects,
        args.output_dir,
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
