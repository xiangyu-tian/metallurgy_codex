"""Build E2 pilot v2 with model-visible label observability guarantees."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
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
from core_freeze.e2_contract_boundaries.hybrid_gate_v1 import (  # noqa: E402
    derive_structural_flags,
)


BASE_POLICY_PATH = HERE / "policy_v1.json"
OVERLAY_PATH = HERE / "policy_v2_observability_overlay.json"
HYBRID_POLICY_PATH = HERE / "hybrid_gate_policy_v1.json"
CONTRACTS_PATH = HERE.parent / "verified_core" / "contracts_v1.json"
DATASET_ID = "E2-CONTRACT-BOUNDARY-PILOT-V2-CANDIDATE-20260731"
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


def combined_policy() -> dict[str, Any]:
    base = load_json(BASE_POLICY_PATH)
    overlay = load_json(OVERLAY_PATH)
    if overlay["base_policy_sha256"] != file_hash(BASE_POLICY_PATH):
        raise ValueError("observability overlay base policy hash mismatch")
    policy = copy.deepcopy(base)
    policy["mutation_rule_version"] = overlay[
        "mutation_rule_version"
    ]
    return policy


def _rekey_task(
    task: dict[str, Any],
    events: list[dict[str, Any]],
) -> None:
    old_task_id = task["task_id"]
    new_task_id = old_task_id.replace("E2P-", "E2V2-", 1)
    event_id_map = {}
    for event in events:
        old_event_id = event["mutation_id"]
        new_event_id = old_event_id.replace("MUT-E2P-", "MUT-E2V2-", 1)
        event_id_map[old_event_id] = new_event_id
        event["mutation_id"] = new_event_id
        event["mutated_task_id"] = new_task_id
    task["task_id"] = new_task_id
    task["mutation_ids"] = [
        event_id_map[event_id] for event_id in task["mutation_ids"]
    ]
    task["task_stage"] = "e2_pilot_v2_observable_candidate"


def build_task(
    sequence: int,
    base_task: dict[str, Any],
    contract: dict[str, Any],
    mutation_types: list[str],
    policy: dict[str, Any],
    overlay: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    task, events = v1.build_task(
        sequence,
        base_task,
        contract,
        mutation_types,
        policy,
    )
    if tuple(mutation_types) == JOINT_MUTATION:
        spec = overlay["joint_mutation_specs"][contract["tool_id"]]
        base_state = v1.make_base_state(base_task, contract)
        v1.deep_update(base_state, spec["final_state_patch"])
        task["structured_state"] = base_state
        joint_id = (
            f"JOINT-{contract['tool_id']}-AMBIGUOUS-AND-OOD-V2"
        )
        task["joint_mutation_spec_id"] = joint_id
        task["label_observability_rationale"] = spec[
            "observability_rationale"
        ]
        for index, event in enumerate(events, 1):
            event["joint_mutation_spec_id"] = joint_id
            event["joint_event_index"] = index
            event["changed_fields"] = {
                "composition_mode": "joint_observable_final_state",
                "final_state_patch": copy.deepcopy(
                    spec["final_state_patch"]
                ),
            }
    _rekey_task(task, events)
    return task, events


def build_dataset() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    policy = combined_policy()
    overlay = load_json(OVERLAY_PATH)
    contracts = v1.contract_map()
    base_tasks = v1.select_base_tasks()
    tasks: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for tool_id in sorted(contracts):
        sequence = 1
        base_task = base_tasks[tool_id]
        contract = contracts[tool_id]
        mutation_sets: list[list[str]] = [[]]
        mutation_sets.extend([[item] for item in v1.SINGLE_MUTATIONS])
        spec = policy["tool_mutation_specs"][tool_id]
        if "unit_field" in spec:
            mutation_sets.extend(
                [["remove_unit"], ["make_unit_ambiguous"]]
            )
        if "unsupported_phase_patch" in spec:
            mutation_sets.append(["unsupported_phase"])
        mutation_sets.extend(
            [list(items) for items in v1.COMBINATION_MUTATIONS]
        )
        for mutation_types in mutation_sets:
            task, task_events = build_task(
                sequence,
                base_task,
                contract,
                mutation_types,
                policy,
                overlay,
            )
            tasks.append(task)
            events.extend(task_events)
            sequence += 1
    return tasks, events


def _values(value: Any) -> list[Any]:
    if (
        isinstance(value, dict)
        and value.get("status") == "ambiguous"
        and isinstance(value.get("candidates"), list)
    ):
        return value["candidates"]
    return [value]


def _formula_elements(formula: str) -> set[str]:
    return set(re.findall(r"[A-Z][a-z]?", formula))


def _all_invalid(values: list[Any], predicate) -> bool:
    return bool(values) and all(predicate(value) for value in values)


def reference_semantic_flags(
    state: dict[str, Any],
    contract: dict[str, Any],
    hybrid_policy: dict[str, Any],
) -> list[str]:
    parameters = state["parameters"]
    context = state["request_context"]
    flags: set[str] = set()
    requested_system = context.get("requested_system")
    if requested_system not in contract["supported_systems"]:
        flags.add("contract_defined_unsupported_system")
    phase_count = context.get("requested_phase_count")
    verified_phase_count = contract.get("verification_scope", {}).get(
        "phase_count"
    )
    if (
        phase_count is not None
        and verified_phase_count is not None
        and phase_count != verified_phase_count
    ):
        flags.add("contract_defined_unsupported_system")
    tool_id = contract["tool_id"]
    ood = False
    if tool_id == "A001" and {
        "source_unit",
        "target_unit",
    } <= set(parameters):
        sources = _values(parameters["source_unit"])
        targets = _values(parameters["target_unit"])
        verified_pairs = {
            tuple(pair)
            for pair in contract["verification_scope"]["unit_pairs"]
        }
        ood = all(
            (source, target) not in verified_pairs
            for source in sources
            for target in targets
        )
    elif tool_id == "A002" and "formula" in parameters:
        ood = _all_invalid(
            _values(parameters["formula"]),
            lambda formula: not isinstance(formula, str)
            or "·" in formula
            or "." in formula,
        )
    elif tool_id == "A003" and "formula" in parameters:
        allowed = set(contract["verification_scope"]["elements"])
        ood = _all_invalid(
            _values(parameters["formula"]),
            lambda formula: not isinstance(formula, str)
            or not _formula_elements(formula) <= allowed,
        )
    elif tool_id == "A004" and "compositions" in parameters:
        def invalid_compositions(value: Any) -> bool:
            if not isinstance(value, dict) or not value:
                return True
            numeric = list(value.values())
            return (
                any(
                    not isinstance(item, (int, float))
                    or isinstance(item, bool)
                    or not math.isfinite(float(item))
                    or item < 0
                    for item in numeric
                )
                or sum(float(item) for item in numeric) <= 0
            )

        ood = _all_invalid(
            _values(parameters["compositions"]),
            invalid_compositions,
        )
    elif tool_id == "B019" and {
        "overall_composition",
        "phase1_composition",
        "phase2_composition",
        "composition_basis",
    } <= set(parameters):
        phase1 = parameters["phase1_composition"]
        phase2 = parameters["phase2_composition"]
        basis = parameters["composition_basis"]

        def invalid_overall(value: Any) -> bool:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return True
            upper = 1.0 if basis == "fraction" else 100.0
            return (
                not math.isfinite(float(value))
                or value < 0
                or value > upper
                or not min(phase1, phase2) <= value <= max(phase1, phase2)
            )

        ood = _all_invalid(
            _values(parameters["overall_composition"]),
            invalid_overall,
        )
    if ood:
        flags.add("contract_defined_out_of_domain")
    semantic = set(hybrid_policy["semantic_flags"])
    if not flags <= semantic:
        raise ValueError("reference semantic validator emitted structural flag")
    return [
        flag
        for flag in hybrid_policy["flag_order"]
        if flag in flags
    ]


def validate_dataset(
    tasks: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    base_policy = combined_policy()
    overlay = load_json(OVERLAY_PATH)
    hybrid_policy = load_json(HYBRID_POLICY_PATH)
    contracts = v1.contract_map()
    structural_allowed = set(hybrid_policy["structural_flags"])
    semantic_allowed = set(hybrid_policy["semantic_flags"])
    errors = []
    task_audit = []
    for task in tasks:
        contract = contracts[task["source_tool_id"]]
        structural = derive_structural_flags(
            task["structured_state"],
            contract,
            hybrid_policy,
        )
        semantic = reference_semantic_flags(
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
        structural_match = set(structural) == set(expected_structural)
        semantic_match = set(semantic) == set(expected_semantic)
        if not structural_match:
            errors.append(
                f"{task['task_id']}: structural expected "
                f"{expected_structural}, observed {structural}"
            )
        if not semantic_match:
            errors.append(
                f"{task['task_id']}: semantic expected "
                f"{expected_semantic}, observed {semantic}"
            )
        task_audit.append(
            {
                "task_id": task["task_id"],
                "expected_structural_flags": expected_structural,
                "observed_structural_flags": structural,
                "expected_semantic_flags": expected_semantic,
                "reference_semantic_flags": semantic,
                "structural_observability_match": structural_match,
                "semantic_observability_match": semantic_match,
            }
        )
    joint_tasks = [
        task
        for task in tasks
        if tuple(task["mutation_types"]) == JOINT_MUTATION
    ]
    checks = [
        {
            "check_id": "CF04-V2-STRUCTURAL-LABEL-OBSERVABILITY",
            "passed": all(
                row["structural_observability_match"]
                for row in task_audit
            ),
            "evidence": {
                "task_count": len(task_audit),
                "mismatch_count": sum(
                    not row["structural_observability_match"]
                    for row in task_audit
                ),
            },
        },
        {
            "check_id": "CF04-V2-SEMANTIC-LABEL-OBSERVABILITY",
            "passed": all(
                row["semantic_observability_match"]
                for row in task_audit
            ),
            "evidence": {
                "task_count": len(task_audit),
                "mismatch_count": sum(
                    not row["semantic_observability_match"]
                    for row in task_audit
                ),
            },
        },
        {
            "check_id": "CF04-V2-JOINT-MUTATION-OBSERVABILITY",
            "passed": (
                len(joint_tasks) == 5
                and all(
                    "joint_mutation_spec_id" in task
                    for task in joint_tasks
                )
            ),
            "evidence": {
                "joint_task_count": len(joint_tasks),
                "tools": sorted(
                    task["source_tool_id"] for task in joint_tasks
                ),
            },
        },
        {
            "check_id": "CF04-V2-RULE-DERIVATION",
            "passed": not errors,
            "evidence": errors,
        },
        {
            "check_id": "CF04-V2-NONCONFIRMATORY",
            "passed": all(
                task["confirmatory_inference_allowed"] is False
                and task["core_frozen"] is False
                for task in tasks
            ),
            "evidence": "all tasks remain candidate-only",
        },
    ]
    return {
        "schema_version": "2.0-candidate",
        "audit_id": "V11-CF04-E2-PILOT-V2-OBSERVABILITY-20260731",
        "dataset_id": DATASET_ID,
        "status": (
            "candidate_passed"
            if all(check["passed"] for check in checks)
            else "failed"
        ),
        "summary": {
            "task_count": len(tasks),
            "mutation_event_count": len(events),
            "joint_task_count": len(joint_tasks),
            "structural_observability_mismatch_count": sum(
                not row["structural_observability_match"]
                for row in task_audit
            ),
            "semantic_observability_mismatch_count": sum(
                not row["semantic_observability_match"]
                for row in task_audit
            ),
            "action_counts": dict(
                sorted(
                    Counter(
                        task["policy_expected_action"] for task in tasks
                    ).items()
                )
            ),
        },
        "checks": checks,
        "task_observability": task_audit,
        "base_policy_sha256": file_hash(BASE_POLICY_PATH),
        "overlay_sha256": file_hash(OVERLAY_PATH),
        "observability_invariant_version": overlay[
            "observability_invariant_version"
        ],
        "human_per_task_labels_used": False,
        "external_api_calls": 0,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }


def run_build(output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    tasks, events = build_dataset()
    audit = validate_dataset(tasks, events)
    if audit["status"] != "candidate_passed":
        raise ValueError("E2 v2 observability audit failed")
    output_dir.mkdir(parents=True)
    task_package = {
        "schema_version": "2.0-candidate",
        "dataset_id": DATASET_ID,
        "dataset_status": "observable_development_candidate",
        "task_count": len(tasks),
        "tasks": tasks,
        "human_per_task_labels_used": False,
        "external_api_calls": 0,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    mutation_package = {
        "schema_version": "2.0-candidate",
        "dataset_id": DATASET_ID,
        "mutation_event_count": len(events),
        "mutation_events": events,
        "core_frozen": False,
    }
    paths = {
        "e2_pilot_tasks_v2.json": task_package,
        "mutation_events_v2.json": mutation_package,
        "observability_audit.json": audit,
    }
    for filename, value in paths.items():
        (output_dir / filename).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    artifacts = [
        {
            "filename": filename,
            "sha256": file_hash(output_dir / filename),
        }
        for filename in paths
    ]
    manifest = {
        "schema_version": "2.0-candidate",
        "dataset_id": DATASET_ID,
        "source_bindings": {
            "base_policy_sha256": file_hash(BASE_POLICY_PATH),
            "overlay_sha256": file_hash(OVERLAY_PATH),
            "hybrid_policy_sha256": file_hash(HYBRID_POLICY_PATH),
            "contracts_sha256": file_hash(CONTRACTS_PATH),
            "builder_sha256": file_hash(Path(__file__)),
        },
        "artifacts": artifacts,
        "external_api_calls": 0,
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
