"""Build an independent, non-executed E2 semantic validation candidate."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parents[1]
PROJECT_ROOT = HERE.parents[2]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from core_freeze.e2_contract_boundaries import build_e2_pilot as v1  # noqa: E402
from core_freeze.e2_contract_boundaries import build_e2_pilot_v2 as v2  # noqa: E402
from core_freeze.e2_contract_boundaries.hybrid_gate_v1 import (  # noqa: E402
    derive_structural_flags,
)


SPLIT_PATH = HERE / "e2_validation_split_v1.json"
BASE_POLICY_PATH = HERE / "policy_v1.json"
HYBRID_POLICY_PATH = HERE / "hybrid_gate_policy_v1.json"
CONTRACTS_PATH = HERE.parent / "verified_core" / "contracts_v1.json"
BASE_TASKS_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "e1b_v2_benefit_r3_20260730"
    / "task_source_snapshot.json"
)
V2_OUTPUT_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_pilot_v2_observable_candidate_20260731"
)
V2_TASKS_PATH = V2_OUTPUT_DIR / "e2_pilot_tasks_v2.json"
V2_MANIFEST_PATH = V2_OUTPUT_DIR / "artifact_manifest.json"
HYBRID_MANIFEST_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_hybrid_gate_v1_candidate_20260731"
    / "artifact_manifest.json"
)
DATASET_ID = "E2-INDEPENDENT-SEMANTIC-VALIDATION-V1-CANDIDATE-20260731"
JOINT_MUTATION = (
    "make_parameter_ambiguous",
    "contract_out_of_domain",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_bindings(split: dict[str, Any]) -> None:
    expected = {
        "source_v2_manifest_sha256": file_hash(V2_MANIFEST_PATH),
        "source_hybrid_manifest_sha256": file_hash(
            HYBRID_MANIFEST_PATH
        ),
        "base_task_snapshot_sha256": file_hash(BASE_TASKS_PATH),
    }
    for key, observed in expected.items():
        if split[key] != observed:
            raise ValueError(f"validation split binding mismatch: {key}")


def _policy(split: dict[str, Any]) -> dict[str, Any]:
    policy = load_json(BASE_POLICY_PATH)
    policy["mutation_rule_version"] = (
        "e2-independent-validation-mutation-v1.0.0-candidate"
    )
    policy["tool_mutation_specs"] = copy.deepcopy(
        split["tool_mutation_specs"]
    )
    return policy


def _selected_base_tasks(
    split: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    by_id = {
        task["task_id"]: task
        for task in load_json(BASE_TASKS_PATH)["tasks"]
    }
    selected = {}
    for tool_id, task_id in split["base_task_selection"].items():
        task = by_id.get(task_id)
        if task is None:
            raise ValueError(f"missing selected base task: {task_id}")
        if task["source_tool_id"] != tool_id:
            raise ValueError(
                f"base task tool mismatch: {tool_id} -> {task_id}"
            )
        selected[tool_id] = task
    return selected


def _build_task(
    sequence: int,
    base_task: dict[str, Any],
    contract: dict[str, Any],
    mutation_types: list[str],
    policy: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    state = v1.make_base_state(base_task, contract)
    tool_id = contract["tool_id"]
    task_id = f"E2VAL-{tool_id}-{sequence:02d}"
    spec = policy["tool_mutation_specs"][tool_id]
    events = []
    for event_index, mutation_type in enumerate(mutation_types, 1):
        changed_fields = v1.apply_mutation(
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
                "random_seed": v1.stable_seed(
                    f"{task_id}:{mutation_type}:{event_index}"
                ),
            }
        )
    if tuple(mutation_types) == JOINT_MUTATION:
        state = v1.make_base_state(base_task, contract)
        v1.deep_update(state, spec["joint_ambiguous_ood_patch"])
        joint_id = f"JOINT-{tool_id}-VALIDATION-AMBIGUOUS-OOD-V1"
        for index, event in enumerate(events, 1):
            event["joint_mutation_spec_id"] = joint_id
            event["joint_event_index"] = index
            event["changed_fields"] = {
                "composition_mode": "joint_observable_final_state",
                "final_state_patch": copy.deepcopy(
                    spec["joint_ambiguous_ood_patch"]
                ),
            }
    flags = v1.derive_flags(mutation_types, policy)
    derived = v1.derive_policy(flags, policy)
    task = {
        "task_id": task_id,
        "base_task_id": base_task["task_id"],
        "base_task_group_id": base_task["base_task_group_id"],
        "source_tool_id": tool_id,
        "source_tool_version": contract["tool_version"],
        "contract_id": contract["contract_id"],
        "contract_hash": contract["contract_hash"],
        "data_layer": "controlled_validation_candidate",
        "split_role": "independent_semantic_validation_candidate",
        "task_stage": "e2_validation_v1_locked_candidate",
        "structured_state": state,
        "mutation_ids": [event["mutation_id"] for event in events],
        "mutation_types": mutation_types,
        "expected_flags": flags,
        **derived,
        "readiness_rule_version": policy["readiness_rule_version"],
        "model_executed": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    if tuple(mutation_types) == JOINT_MUTATION:
        task["joint_mutation_spec_id"] = (
            f"JOINT-{tool_id}-VALIDATION-AMBIGUOUS-OOD-V1"
        )
    return task, events


def build_dataset() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    split = load_json(SPLIT_PATH)
    _source_bindings(split)
    policy = _policy(split)
    contracts = v1.contract_map()
    base_tasks = _selected_base_tasks(split)
    if set(base_tasks) != set(contracts):
        raise ValueError("validation base task selection is incomplete")
    tasks = []
    events = []
    for tool_id in sorted(contracts):
        for sequence, mutations in enumerate(split["task_matrix"], 1):
            task, task_events = _build_task(
                sequence,
                base_tasks[tool_id],
                contracts[tool_id],
                list(mutations),
                policy,
            )
            tasks.append(task)
            events.extend(task_events)
    return tasks, events


def review_v2_source() -> dict[str, Any]:
    manifest = load_json(V2_MANIFEST_PATH)
    manifest_failures = []
    for artifact in manifest["artifacts"]:
        path = V2_OUTPUT_DIR / artifact["filename"]
        if not path.is_file():
            manifest_failures.append(f"missing:{artifact['filename']}")
        elif file_hash(path) != artifact["sha256"]:
            manifest_failures.append(f"hash:{artifact['filename']}")
    rebuilt_tasks, rebuilt_events = v2.build_dataset()
    stored = load_json(V2_TASKS_PATH)
    stored_events = load_json(
        V2_OUTPUT_DIR / "mutation_events_v2.json"
    )
    audit = v2.validate_dataset(rebuilt_tasks, rebuilt_events)
    checks = {
        "manifest_hashes_valid": not manifest_failures,
        "stored_tasks_match_rebuild": (
            stored["tasks"] == rebuilt_tasks
        ),
        "stored_events_match_rebuild": (
            stored_events["mutation_events"] == rebuilt_events
        ),
        "label_observability_passed": (
            audit["status"] == "candidate_passed"
            and audit["summary"][
                "structural_observability_mismatch_count"
            ]
            == 0
            and audit["summary"][
                "semantic_observability_mismatch_count"
            ]
            == 0
        ),
    }
    passed = all(checks.values())
    return {
        "schema_version": "1.0-candidate",
        "review_id": "E2-V2-DEVELOPMENT-SOURCE-REVIEW-20260731",
        "source_dataset_id": stored["dataset_id"],
        "source_manifest_sha256": file_hash(V2_MANIFEST_PATH),
        "decision": (
            "accepted_as_locked_development_source_for_validation"
            if passed
            else "rejected"
        ),
        "checks": checks,
        "manifest_failures": manifest_failures,
        "task_count": len(rebuilt_tasks),
        "mutation_event_count": len(rebuilt_events),
        "scope_limit": (
            "development source lock only; not CF-04 pass and not "
            "Core Frozen"
        ),
        "external_api_calls": 0,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }


def audit_independence(
    tasks: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    split = load_json(SPLIT_PATH)
    policy = _policy(split)
    development_policy = load_json(BASE_POLICY_PATH)
    development_overlay = load_json(v2.OVERLAY_PATH)
    hybrid_policy = load_json(HYBRID_POLICY_PATH)
    contracts = v1.contract_map()
    development = load_json(V2_TASKS_PATH)["tasks"]
    development_events = load_json(
        V2_OUTPUT_DIR / "mutation_events_v2.json"
    )["mutation_events"]
    development_task_ids = {row["task_id"] for row in development}
    development_event_ids = {
        row["mutation_id"] for row in development_events
    }
    development_base_ids = {row["base_task_id"] for row in development}
    development_group_ids = {
        row["base_task_group_id"] for row in development
    }
    development_state_hashes = {
        canonical_hash(row["structured_state"]) for row in development
    }
    structural_allowed = set(hybrid_policy["structural_flags"])
    semantic_allowed = set(hybrid_policy["semantic_flags"])
    observability_errors = []
    action_errors = []
    task_audit = []
    for task in tasks:
        contract = contracts[task["source_tool_id"]]
        structural = derive_structural_flags(
            task["structured_state"],
            contract,
            hybrid_policy,
        )
        semantic = v2.reference_semantic_flags(
            task["structured_state"],
            contract,
            hybrid_policy,
        )
        expected_structural = [
            flag
            for flag in task["expected_flags"]
            if flag in structural_allowed
        ]
        expected_semantic = [
            flag
            for flag in task["expected_flags"]
            if flag in semantic_allowed
        ]
        if set(structural) != set(expected_structural):
            observability_errors.append(
                f"{task['task_id']}:structural"
            )
        if set(semantic) != set(expected_semantic):
            observability_errors.append(f"{task['task_id']}:semantic")
        recomputed = v1.derive_policy(task["expected_flags"], policy)
        if any(task[key] != value for key, value in recomputed.items()):
            action_errors.append(task["task_id"])
        task_audit.append(
            {
                "task_id": task["task_id"],
                "structured_state_sha256": canonical_hash(
                    task["structured_state"]
                ),
                "expected_structural_flags": expected_structural,
                "observed_structural_flags": structural,
                "expected_semantic_flags": expected_semantic,
                "reference_semantic_flags": semantic,
            }
        )
    task_ids = {row["task_id"] for row in tasks}
    event_ids = {row["mutation_id"] for row in events}
    base_ids = {row["base_task_id"] for row in tasks}
    group_ids = {row["base_task_group_id"] for row in tasks}
    state_hashes = {
        canonical_hash(row["structured_state"]) for row in tasks
    }
    semantic_positive_count = sum(
        any(flag in semantic_allowed for flag in row["expected_flags"])
        for row in tasks
    )
    semantic_negative_count = len(tasks) - semantic_positive_count
    distinct_boundary_spec_tools = []
    for tool_id, validation_spec in split[
        "tool_mutation_specs"
    ].items():
        development_spec = development_policy[
            "tool_mutation_specs"
        ][tool_id]
        development_joint = development_overlay[
            "joint_mutation_specs"
        ][tool_id]["final_state_patch"]
        if (
            validation_spec["ambiguous_candidates"]
            != development_spec["ambiguous_candidates"]
            and validation_spec["out_of_domain_patch"]
            != development_spec["out_of_domain_patch"]
            and validation_spec["unsupported_system_patch"]
            != development_spec["unsupported_system_patch"]
            and validation_spec["joint_ambiguous_ood_patch"]
            != development_joint
        ):
            distinct_boundary_spec_tools.append(tool_id)
    checks = [
        {
            "check_id": "CF04-VAL-UNIQUE-IDS",
            "passed": (
                len(task_ids) == len(tasks)
                and len(event_ids) == len(events)
            ),
            "evidence": {
                "task_count": len(tasks),
                "unique_task_count": len(task_ids),
                "event_count": len(events),
                "unique_event_count": len(event_ids),
            },
        },
        {
            "check_id": "CF04-VAL-TASK-ID-DISJOINT",
            "passed": not task_ids & development_task_ids,
            "evidence": sorted(task_ids & development_task_ids),
        },
        {
            "check_id": "CF04-VAL-EVENT-ID-DISJOINT",
            "passed": not event_ids & development_event_ids,
            "evidence": sorted(event_ids & development_event_ids),
        },
        {
            "check_id": "CF04-VAL-BASE-TASK-DISJOINT",
            "passed": not base_ids & development_base_ids,
            "evidence": sorted(base_ids & development_base_ids),
        },
        {
            "check_id": "CF04-VAL-BASE-GROUP-DISJOINT",
            "passed": not group_ids & development_group_ids,
            "evidence": sorted(group_ids & development_group_ids),
        },
        {
            "check_id": "CF04-VAL-STATE-DISJOINT",
            "passed": (
                not state_hashes & development_state_hashes
                and len(state_hashes) == len(tasks)
            ),
            "evidence": {
                "development_overlap": sorted(
                    state_hashes & development_state_hashes
                ),
                "validation_state_count": len(tasks),
                "unique_validation_state_count": len(state_hashes),
            },
        },
        {
            "check_id": "CF04-VAL-BOUNDARY-SPEC-DISJOINT",
            "passed": set(distinct_boundary_spec_tools) == set(contracts),
            "evidence": sorted(distinct_boundary_spec_tools),
        },
        {
            "check_id": "CF04-VAL-LABEL-OBSERVABILITY",
            "passed": not observability_errors,
            "evidence": observability_errors,
        },
        {
            "check_id": "CF04-VAL-ACTION-RECOMPUTATION",
            "passed": not action_errors,
            "evidence": action_errors,
        },
        {
            "check_id": "CF04-VAL-SEMANTIC-BALANCE",
            "passed": (
                semantic_positive_count == semantic_negative_count == 20
            ),
            "evidence": {
                "semantic_positive_count": semantic_positive_count,
                "semantic_negative_count": semantic_negative_count,
            },
        },
        {
            "check_id": "CF04-VAL-FIVE-TOOL-COVERAGE",
            "passed": {
                row["source_tool_id"] for row in tasks
            }
            == set(contracts),
            "evidence": sorted(contracts),
        },
        {
            "check_id": "CF04-VAL-NOT-EXECUTED",
            "passed": (
                split["external_api_execution_authorized"] is False
                and split["model_execution_count"] == 0
                and all(row["model_executed"] is False for row in tasks)
            ),
            "evidence": "model_execution_count=0",
        },
    ]
    action_counts = Counter(
        row["policy_expected_action"] for row in tasks
    )
    return {
        "schema_version": "1.0-candidate",
        "audit_id": "E2-INDEPENDENT-VALIDATION-AUDIT-V1-20260731",
        "dataset_id": DATASET_ID,
        "status": (
            "candidate_passed"
            if all(row["passed"] for row in checks)
            else "failed"
        ),
        "summary": {
            "task_count": len(tasks),
            "mutation_event_count": len(events),
            "tool_count": len(
                {row["source_tool_id"] for row in tasks}
            ),
            "semantic_positive_count": semantic_positive_count,
            "semantic_negative_count": semantic_negative_count,
            "multi_label_count": sum(
                len(row["expected_flags"]) >= 2 for row in tasks
            ),
            "action_counts": dict(sorted(action_counts.items())),
            "development_state_overlap_count": len(
                state_hashes & development_state_hashes
            ),
            "observability_error_count": len(observability_errors),
        },
        "checks": checks,
        "task_audit": task_audit,
        "limitations": [
            "contracts and tool identities remain shared with development",
            "this tests within-tool case generalization, not unseen-tool generalization",
            "temperature, pressure and model-card OOD are not covered",
            "no LLM has executed this locked candidate",
        ],
        "external_api_calls": 0,
        "external_api_execution_authorized": False,
        "model_performance_claim_allowed": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }


def run_build(output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    source_review = review_v2_source()
    if source_review["decision"] != (
        "accepted_as_locked_development_source_for_validation"
    ):
        raise ValueError("E2 v2 source review failed")
    tasks, events = build_dataset()
    audit = audit_independence(tasks, events)
    if audit["status"] != "candidate_passed":
        raise ValueError("E2 independent validation audit failed")
    split = load_json(SPLIT_PATH)
    output_dir.mkdir(parents=True)
    payloads = {
        "validation_split_snapshot.json": split,
        "e2_validation_tasks_v1.json": {
            "schema_version": "1.0-candidate",
            "dataset_id": DATASET_ID,
            "dataset_status": "locked_validation_candidate_not_executed",
            "split_id": split["split_id"],
            "task_count": len(tasks),
            "tasks": tasks,
            "model_execution_count": 0,
            "external_api_calls": 0,
            "confirmatory_inference_allowed": False,
            "core_frozen": False,
        },
        "mutation_events_validation_v1.json": {
            "schema_version": "1.0-candidate",
            "dataset_id": DATASET_ID,
            "mutation_event_count": len(events),
            "mutation_events": events,
            "core_frozen": False,
        },
        "v2_source_review_record.json": source_review,
        "independence_audit.json": audit,
    }
    for filename, payload in payloads.items():
        (output_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    manifest = {
        "schema_version": "1.0-candidate",
        "dataset_id": DATASET_ID,
        "source_bindings": {
            "split_sha256": file_hash(SPLIT_PATH),
            "v2_manifest_sha256": file_hash(V2_MANIFEST_PATH),
            "hybrid_manifest_sha256": file_hash(
                HYBRID_MANIFEST_PATH
            ),
            "contracts_sha256": file_hash(CONTRACTS_PATH),
            "builder_sha256": file_hash(Path(__file__)),
        },
        "artifacts": [
            {
                "filename": filename,
                "sha256": file_hash(output_dir / filename),
            }
            for filename in payloads
        ],
        "external_api_calls": 0,
        "external_api_execution_authorized": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    (output_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    audit = run_build(args.output_dir.resolve())
    print(json.dumps(audit["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
