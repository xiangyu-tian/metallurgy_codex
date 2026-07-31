"""Build and audit a deterministic E2 contract-boundary pilot."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
CORE_FREEZE_DIR = HERE.parent
PROJECT_ROOT = CORE_FREEZE_DIR.parents[1]
POLICY_PATH = HERE / "policy_v1.json"
CONTRACTS_PATH = (
    CORE_FREEZE_DIR / "verified_core" / "contracts_v1.json"
)
BASE_TASKS_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "e1b_v2_benefit_r3_20260730"
    / "task_source_snapshot.json"
)

SINGLE_MUTATIONS = (
    "remove_required_parameter",
    "make_parameter_ambiguous",
    "contract_out_of_domain",
    "unsupported_system",
    "unavailable_tool",
    "version_mismatch",
)
COMBINATION_MUTATIONS = (
    ("remove_required_parameter", "unavailable_tool"),
    ("make_parameter_ambiguous", "contract_out_of_domain"),
    ("contract_out_of_domain", "unavailable_tool"),
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def stable_seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def select_base_tasks() -> dict[str, dict[str, Any]]:
    snapshot = load_json(BASE_TASKS_PATH)
    selected: dict[str, dict[str, Any]] = {}
    for task in snapshot["tasks"]:
        selected.setdefault(task["source_tool_id"], task)
    return selected


def contract_map() -> dict[str, dict[str, Any]]:
    return {
        row["tool_id"]: row
        for row in load_json(CONTRACTS_PATH)["contracts"]
        if row.get("tool_status") == "verified_core"
    }


def make_base_state(
    task: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    return {
        "parameters": copy.deepcopy(task["canonical_inputs"]),
        "request_context": {
            "requested_tool_id": contract["tool_id"],
            "requested_tool_version": contract["tool_version"],
            "requested_system": contract["supported_systems"][0],
        },
        "service_status": contract["service_status"],
    }


def deep_update(target: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if (
            isinstance(value, dict)
            and isinstance(target.get(key), dict)
        ):
            deep_update(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


def apply_mutation(
    state: dict[str, Any],
    mutation_type: str,
    contract: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    changed_fields: dict[str, Any] = {}
    if mutation_type == "remove_required_parameter":
        field = contract["required_inputs"][0]
        previous = state["parameters"].pop(field, None)
        changed_fields[f"parameters.{field}"] = {
            "before": previous,
            "after": "__MISSING__",
        }
    elif mutation_type == "remove_unit":
        field = spec["unit_field"]
        previous = state["parameters"].pop(field, None)
        changed_fields[f"parameters.{field}"] = {
            "before": previous,
            "after": "__MISSING__",
        }
    elif mutation_type in {
        "make_parameter_ambiguous",
        "make_unit_ambiguous",
    }:
        if mutation_type == "make_unit_ambiguous":
            field = spec["unit_field"]
            candidates = spec["unit_ambiguous_candidates"]
        else:
            field = spec["ambiguous_field"]
            candidates = spec["ambiguous_candidates"]
        previous = state["parameters"].get(field)
        marker = {
            "status": "ambiguous",
            "candidates": copy.deepcopy(candidates),
        }
        state["parameters"][field] = marker
        changed_fields[f"parameters.{field}"] = {
            "before": previous,
            "after": marker,
        }
    elif mutation_type == "contract_out_of_domain":
        before = copy.deepcopy(state)
        deep_update(state, spec["out_of_domain_patch"])
        changed_fields["state_patch"] = {
            "before": before,
            "after": copy.deepcopy(state),
        }
    elif mutation_type == "unsupported_system":
        before = copy.deepcopy(state)
        deep_update(state, spec["unsupported_system_patch"])
        changed_fields["state_patch"] = {
            "before": before,
            "after": copy.deepcopy(state),
        }
    elif mutation_type == "unsupported_phase":
        before = copy.deepcopy(state)
        deep_update(state, spec["unsupported_phase_patch"])
        changed_fields["state_patch"] = {
            "before": before,
            "after": copy.deepcopy(state),
        }
    elif mutation_type == "unavailable_tool":
        previous = state["service_status"]
        state["service_status"] = "unavailable"
        changed_fields["service_status"] = {
            "before": previous,
            "after": "unavailable",
        }
    elif mutation_type == "version_mismatch":
        previous = state["request_context"]["requested_tool_version"]
        replacement = f"{contract['tool_version']}-mismatch"
        state["request_context"]["requested_tool_version"] = replacement
        changed_fields["request_context.requested_tool_version"] = {
            "before": previous,
            "after": replacement,
        }
    else:
        raise ValueError(f"unsupported mutation type: {mutation_type}")
    return changed_fields


def derive_flags(
    mutation_types: list[str],
    policy: dict[str, Any],
) -> list[str]:
    flags: set[str] = set()
    for mutation_type in mutation_types:
        flags.update(
            policy["mutation_types"][mutation_type]["flags"]
        )
    flag_order = policy["flags"]
    return [flag for flag in flag_order if flag in flags]


def derive_policy(
    flags: list[str],
    policy: dict[str, Any],
) -> dict[str, Any]:
    flag_set = set(flags)
    for row in policy["priority"]:
        relevant = set(row["any_flags"])
        if (relevant and flag_set & relevant) or (
            not relevant and not flag_set
        ):
            return {
                "primary_status": row["primary_status"],
                "allowed_actions": row["allowed_actions"],
                "policy_expected_action": row[
                    "policy_expected_action"
                ],
            }
    raise ValueError(f"no policy row for flags: {flags}")


def build_task(
    sequence: int,
    base_task: dict[str, Any],
    contract: dict[str, Any],
    mutation_types: list[str],
    policy: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    state = make_base_state(base_task, contract)
    tool_id = contract["tool_id"]
    task_id = f"E2P-{tool_id}-{sequence:02d}"
    spec = policy["tool_mutation_specs"][tool_id]
    events = []
    for event_index, mutation_type in enumerate(mutation_types, 1):
        changed_fields = apply_mutation(
            state,
            mutation_type,
            contract,
            spec,
        )
        events.append(
            {
                "mutation_id": f"MUT-{task_id}-{event_index:02d}",
                "base_task_id": base_task["task_id"],
                "mutated_task_id": task_id,
                "mutation_type": mutation_type,
                "mutation_rule_version": policy[
                    "mutation_rule_version"
                ],
                "changed_fields": changed_fields,
                "expected_flag_effects": policy["mutation_types"][
                    mutation_type
                ]["flags"],
                "random_seed": stable_seed(
                    f"{task_id}:{mutation_type}:{event_index}"
                ),
            }
        )
    flags = derive_flags(mutation_types, policy)
    derived = derive_policy(flags, policy)
    task = {
        "task_id": task_id,
        "base_task_id": base_task["task_id"],
        "base_task_group_id": base_task["base_task_group_id"],
        "source_tool_id": tool_id,
        "source_tool_version": contract["tool_version"],
        "contract_id": contract["contract_id"],
        "contract_hash": contract["contract_hash"],
        "data_layer": "controlled_confirmatory_candidate",
        "task_stage": "e2_pilot_candidate",
        "structured_state": state,
        "mutation_ids": [event["mutation_id"] for event in events],
        "mutation_types": mutation_types,
        "expected_flags": flags,
        **derived,
        "readiness_rule_version": policy[
            "readiness_rule_version"
        ],
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    return task, events


def build_dataset() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    policy = load_json(POLICY_PATH)
    contracts = contract_map()
    base_tasks = select_base_tasks()
    tasks: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for tool_id in sorted(contracts):
        sequence = 1
        base_task = base_tasks[tool_id]
        contract = contracts[tool_id]
        task, rows = build_task(
            sequence, base_task, contract, [], policy
        )
        tasks.append(task)
        events.extend(rows)
        sequence += 1
        for mutation_type in SINGLE_MUTATIONS:
            task, rows = build_task(
                sequence,
                base_task,
                contract,
                [mutation_type],
                policy,
            )
            tasks.append(task)
            events.extend(rows)
            sequence += 1
        spec = policy["tool_mutation_specs"][tool_id]
        if "unit_field" in spec:
            for mutation_type in ("remove_unit", "make_unit_ambiguous"):
                task, rows = build_task(
                    sequence,
                    base_task,
                    contract,
                    [mutation_type],
                    policy,
                )
                tasks.append(task)
                events.extend(rows)
                sequence += 1
        if "unsupported_phase_patch" in spec:
            task, rows = build_task(
                sequence,
                base_task,
                contract,
                ["unsupported_phase"],
                policy,
            )
            tasks.append(task)
            events.extend(rows)
            sequence += 1
        for mutation_types in COMBINATION_MUTATIONS:
            task, rows = build_task(
                sequence,
                base_task,
                contract,
                list(mutation_types),
                policy,
            )
            tasks.append(task)
            events.extend(rows)
            sequence += 1
    return tasks, events


def validate_dataset(
    tasks: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    policy = load_json(POLICY_PATH)
    contracts = contract_map()
    task_ids = [task["task_id"] for task in tasks]
    event_ids = [event["mutation_id"] for event in events]
    event_by_id = {event["mutation_id"]: event for event in events}
    errors: list[str] = []
    for task in tasks:
        mutation_types = [
            event_by_id[mutation_id]["mutation_type"]
            for mutation_id in task["mutation_ids"]
        ]
        expected_flags = derive_flags(mutation_types, policy)
        expected_policy = derive_policy(expected_flags, policy)
        if mutation_types != task["mutation_types"]:
            errors.append(f"{task['task_id']}: mutation order mismatch")
        if task["expected_flags"] != expected_flags:
            errors.append(f"{task['task_id']}: flag derivation mismatch")
        for key, value in expected_policy.items():
            if task[key] != value:
                errors.append(
                    f"{task['task_id']}: policy mismatch for {key}"
                )
        contract = contracts[task["source_tool_id"]]
        if task["contract_hash"] != contract["contract_hash"]:
            errors.append(f"{task['task_id']}: contract hash mismatch")
    mutation_counts = Counter(
        event["mutation_type"] for event in events
    )
    flag_counts = Counter(
        flag for task in tasks for flag in task["expected_flags"]
    )
    action_counts = Counter(
        task["policy_expected_action"] for task in tasks
    )
    required_core_types = {
        "remove_required_parameter",
        "make_parameter_ambiguous",
        "contract_out_of_domain",
        "unsupported_system",
        "unavailable_tool",
        "version_mismatch",
    }
    coverage_gaps = [
        {
            "mutation_type": "out_of_temperature_range",
            "status": "not_applicable_no_verified_contract_field",
            "eligible_tool_count": 0,
        },
        {
            "mutation_type": "out_of_pressure_range",
            "status": "not_applicable_no_verified_contract_field",
            "eligible_tool_count": 0,
        },
        {
            "mutation_type": "model_card_defined_ood",
            "status": "not_applicable_no_verified_neural_model",
            "eligible_tool_count": 0,
        },
    ]
    checks = [
        {
            "check_id": "CF04-UNIQUE-TASKS",
            "passed": len(task_ids) == len(set(task_ids)),
            "evidence": f"task_count={len(task_ids)}",
        },
        {
            "check_id": "CF04-UNIQUE-MUTATIONS",
            "passed": len(event_ids) == len(set(event_ids)),
            "evidence": f"mutation_event_count={len(event_ids)}",
        },
        {
            "check_id": "CF04-CORE-TYPE-COVERAGE",
            "passed": required_core_types <= set(mutation_counts),
            "evidence": dict(sorted(mutation_counts.items())),
        },
        {
            "check_id": "CF04-FIVE-TOOL-COVERAGE",
            "passed": {
                task["source_tool_id"] for task in tasks
            }
            == set(contracts),
            "evidence": sorted(contracts),
        },
        {
            "check_id": "CF04-MULTI-LABEL-COVERAGE",
            "passed": sum(
                len(task["expected_flags"]) >= 2 for task in tasks
            )
            >= 15,
            "evidence": {
                "multi_label_task_count": sum(
                    len(task["expected_flags"]) >= 2 for task in tasks
                )
            },
        },
        {
            "check_id": "CF04-ACTION-COVERAGE",
            "passed": {"call", "clarify", "refuse"} <= set(action_counts),
            "evidence": dict(sorted(action_counts.items())),
        },
        {
            "check_id": "CF04-RULE-RECOMPUTATION",
            "passed": not errors,
            "evidence": errors,
        },
        {
            "check_id": "CF04-NO-HUMAN-PER-TASK-LABELS",
            "passed": all(
                task["readiness_rule_version"]
                == policy["readiness_rule_version"]
                for task in tasks
            ),
            "evidence": policy["readiness_rule_version"],
        },
        {
            "check_id": "CF04-NOT-CONFIRMATORY",
            "passed": all(
                task["confirmatory_inference_allowed"] is False
                and task["core_frozen"] is False
                for task in tasks
            ),
            "evidence": "all pilot tasks preserve candidate status",
        },
    ]
    candidate_passed = all(row["passed"] for row in checks)
    return {
        "schema_version": "1.0",
        "audit_id": "V11-CF04-E2-PILOT-AUDIT-20260731",
        "check_id": "CF-04",
        "status": "in_progress" if candidate_passed else "failed",
        "candidate_evidence_status": (
            "passed" if candidate_passed else "failed"
        ),
        "summary": {
            "task_count": len(tasks),
            "ready_task_count": sum(
                not task["expected_flags"] for task in tasks
            ),
            "mutated_task_count": sum(
                bool(task["expected_flags"]) for task in tasks
            ),
            "multi_label_task_count": sum(
                len(task["expected_flags"]) >= 2 for task in tasks
            ),
            "mutation_event_count": len(events),
            "tool_count": len(contracts),
            "mutation_type_counts": dict(
                sorted(mutation_counts.items())
            ),
            "flag_counts": dict(sorted(flag_counts.items())),
            "action_counts": dict(sorted(action_counts.items())),
        },
        "checks": checks,
        "coverage_gaps": coverage_gaps,
        "pending_requirements": [
            "add a verified contract with temperature range",
            "add a verified contract with pressure range",
            "add a verified neural model with model-card OOD boundary",
            "execute E2 model-policy pilot after task package review",
        ],
        "human_free_truth_derivation": True,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }


def run_build(output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    tasks, events = build_dataset()
    audit = validate_dataset(tasks, events)
    policy = load_json(POLICY_PATH)
    task_package = {
        "schema_version": "1.0",
        "dataset_id": "E2-CONTRACT-BOUNDARY-PILOT-V1-20260731",
        "dataset_status": "pilot_candidate",
        "mutation_rule_version": policy["mutation_rule_version"],
        "readiness_rule_version": policy["readiness_rule_version"],
        "task_count": len(tasks),
        "tasks": tasks,
        "human_per_task_labels_used": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    mutation_package = {
        "schema_version": "1.0",
        "dataset_id": task_package["dataset_id"],
        "mutation_event_count": len(events),
        "mutation_events": events,
        "core_frozen": False,
    }
    coverage = {
        "schema_version": "1.0",
        "dataset_id": task_package["dataset_id"],
        "covered_mutation_types": sorted(
            audit["summary"]["mutation_type_counts"]
        ),
        "coverage_gaps": audit["coverage_gaps"],
        "cf04_status": audit["status"],
        "core_frozen": False,
    }
    output_dir.mkdir(parents=True)
    payloads = {
        "e2_pilot_tasks.json": task_package,
        "mutation_events.json": mutation_package,
        "coverage_report.json": coverage,
        "audit_report.json": audit,
    }
    for filename, payload in payloads.items():
        (output_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    sources = [
        POLICY_PATH,
        CONTRACTS_PATH,
        BASE_TASKS_PATH,
        Path(__file__),
    ]
    manifest = {
        "schema_version": "1.0",
        "dataset_id": task_package["dataset_id"],
        "artifacts": [
            {
                "filename": filename,
                "sha256": file_hash(output_dir / filename),
            }
            for filename in payloads
        ],
        "source_artifacts": [
            {"filename": relative(path), "sha256": file_hash(path)}
            for path in sources
        ],
        "cf04_status": audit["status"],
        "core_frozen": False,
    }
    (output_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=(
            PROJECT_ROOT
            / "outputs"
            / "v11_cf04_e2_pilot_20260731"
        ),
    )
    args = parser.parse_args()
    audit = run_build(args.output_dir)
    print(
        json.dumps(
            {
                "audit_id": audit["audit_id"],
                "cf04_status": audit["status"],
                "candidate_evidence_status": audit[
                    "candidate_evidence_status"
                ],
                "summary": audit["summary"],
                "coverage_gaps": audit["coverage_gaps"],
                "core_frozen": audit["core_frozen"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if audit["candidate_evidence_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
