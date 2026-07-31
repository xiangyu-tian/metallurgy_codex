"""Generate the independent E1c end-to-end task set.

Reference answers are produced by the independent equations in the E1b v2
generator.  Production tools are not imported here; they are checked by the
separate E1c validator.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parents[1]
PROJECT_ROOT = HERE.parents[2]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from core_freeze.e1b_v2.apply_candidate_gate_policy import (  # noqa: E402
    classify_task,
    file_hash,
    load_json,
    validate_policy,
    write_json,
)
from core_freeze.e1b_v2.generate_e1b_v2 import (  # noqa: E402
    build_a001,
    build_a002,
    build_a003,
    build_a004,
    build_b019,
    contract_map,
)


POLICY_SHA256 = (
    "4d34ddc0a8d53d46f0aabf1469469dab243b9ddb6c03a5e8e849b9763801c1d5"
)
EXPECTED_TOOL_COUNTS = {
    "A001": 10,
    "A002": 10,
    "A003": 20,
    "A004": 12,
    "B019": 8,
}
EXPECTED_SPLIT_COUNTS = {
    "runner_development": 24,
    "end_to_end_evaluation": 36,
}
EXPERIMENTAL_CONDITIONS = [
    "no_tool",
    "forced_verified_oracle_parameters",
    "model_gate_oracle_parameters",
    "oracle_gate_model_parameters",
    "direct_fc",
    "boundary_guided_fc",
]


def project_relative(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def _rename_tasks(tasks: list[dict[str, Any]], tool_id: str) -> None:
    for index, task in enumerate(tasks, start=1):
        task_id = f"E1C-{tool_id}-{index:03d}"
        task["task_id"] = task_id
        task["task_family_id"] = f"E1C-{tool_id}"
        task["task_pair_id"] = f"PAIR-{task_id}"
        task["random_seed"] = int(
            __import__("hashlib").sha256(task_id.encode("utf-8")).hexdigest()[:8],
            16,
        )
        task["scoring_rule"]["rule_id"] = f"E1C-{tool_id}-PRIMARY-v1"
        task["confirmatory_eligibility"] = "e1c_development_candidate"


def build_tasks(
    seeds_doc: dict[str, Any],
    contracts_doc: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    contracts = contract_map(contracts_doc)
    required = set(EXPECTED_TOOL_COUNTS)
    if not required.issubset(contracts):
        raise ValueError(
            f"missing verified contracts: {sorted(required - set(contracts))}"
        )
    builders = [
        ("A001", build_a001),
        ("A002", build_a002),
        ("A003", build_a003),
        ("A004", build_a004),
        ("B019", build_b019),
    ]
    tasks: list[dict[str, Any]] = []
    for tool_id, builder in builders:
        rows = builder(seeds_doc, contracts)
        _rename_tasks(rows, tool_id)
        for task in rows:
            decision = classify_task(task, policy)
            task["frozen_policy_decision"] = {
                "policy_id": policy["policy_id"],
                "policy_version": policy["policy_version"],
                "policy_sha256": POLICY_SHA256,
                "action": decision["action"],
                "rule_id": decision["rule_id"],
                "reason_code": decision["reason_code"],
            }
        tasks.extend(rows)
    return tasks


def structural_errors(
    tasks: list[dict[str, Any]],
    contracts_doc: dict[str, Any],
    e1b_group_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    contracts = contract_map(contracts_doc)
    if Counter(task["source_tool_id"] for task in tasks) != Counter(
        EXPECTED_TOOL_COUNTS
    ):
        errors.append("unexpected task counts by tool")
    if Counter(task["split"] for task in tasks) != Counter(
        EXPECTED_SPLIT_COUNTS
    ):
        errors.append("unexpected task counts by split")
    task_ids = [task["task_id"] for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        errors.append("duplicate task id")

    group_splits: dict[str, set[str]] = defaultdict(set)
    for task in tasks:
        group = task["base_task_group_id"]
        group_splits[group].add(task["split"])
        if group in e1b_group_ids:
            errors.append(f"{task['task_id']}: reuses E1b group {group}")
        contract = contracts.get(task["source_tool_id"])
        if not contract:
            errors.append(f"{task['task_id']}: unverified source tool")
            continue
        if task["contract_hash"] != contract["contract_hash"]:
            errors.append(f"{task['task_id']}: contract hash mismatch")
        if task["reference_execution"]["production_code_imported"] is not False:
            errors.append(f"{task['task_id']}: reference imports production")
        if task["canonical_inputs"] != task["expected_parameters"]:
            errors.append(f"{task['task_id']}: expected parameters mismatch")
        decision = task["frozen_policy_decision"]
        if decision["policy_sha256"] != POLICY_SHA256:
            errors.append(f"{task['task_id']}: policy hash mismatch")
    leaking = [group for group, splits in group_splits.items() if len(splits) > 1]
    if leaking:
        errors.append(f"groups cross splits: {sorted(leaking)}")

    a003_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        if task["source_tool_id"] == "A003":
            a003_groups[task["base_task_group_id"]].append(task)
    for group, rows in a003_groups.items():
        if len(rows) != 2:
            errors.append(f"{group}: A003 pair size is not 2")
        if {row["precision_policy"] for row in rows} != {
            "strict_versioned",
            "approximate_educational",
        }:
            errors.append(f"{group}: incomplete A003 precision pair")
        if len({row["split"] for row in rows}) != 1:
            errors.append(f"{group}: A003 precision pair crosses split")

    action_split_counts = Counter(
        (task["split"], task["frozen_policy_decision"]["action"])
        for task in tasks
    )
    expected_actions = Counter(
        {
            ("runner_development", "CALL_VERIFIED_TOOL"): 6,
            ("runner_development", "ANSWER_WITHOUT_TOOL"): 18,
            ("end_to_end_evaluation", "CALL_VERIFIED_TOOL"): 10,
            ("end_to_end_evaluation", "ANSWER_WITHOUT_TOOL"): 26,
        }
    )
    if action_split_counts != expected_actions:
        errors.append(
            f"unexpected policy action distribution: {dict(action_split_counts)}"
        )
    return errors


def generate(
    seeds_path: Path,
    contracts_path: Path,
    policy_path: Path,
    e1b_tasks_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    seeds = load_json(seeds_path)
    contracts = load_json(contracts_path)
    policy = load_json(policy_path)
    validate_policy(policy)
    if file_hash(policy_path) != POLICY_SHA256:
        raise ValueError("candidate policy v1 hash mismatch")
    e1b_doc = load_json(e1b_tasks_path)
    e1b_groups = {
        task["base_task_group_id"] for task in e1b_doc["tasks"]
    }
    tasks = build_tasks(seeds, contracts, policy)
    errors = structural_errors(tasks, contracts, e1b_groups)
    if errors:
        raise ValueError("; ".join(errors))

    output_dir.mkdir(parents=True, exist_ok=True)
    tasks_path = output_dir / "e1c_tasks_v1.json"
    tasks_doc = {
        "schema_version": "1.0",
        "dataset_id": seeds["dataset_id"],
        "dataset_status": "prepared_pre_api",
        "protocol_id": "E1C-END-TO-END-PROTOCOL-V1",
        "protocol_sha256": file_hash(HERE / "protocol_v1.md"),
        "generator_version": seeds["generator_version"],
        "generated_at": seeds["generated_at"],
        "task_count": len(tasks),
        "task_count_by_split": dict(
            sorted(Counter(task["split"] for task in tasks).items())
        ),
        "experimental_conditions": EXPERIMENTAL_CONDITIONS,
        "frozen_policy_id": policy["policy_id"],
        "frozen_policy_sha256": POLICY_SHA256,
        "evaluation_split_opened": False,
        "tasks": tasks,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    write_json(tasks_path, tasks_doc)

    report_path = output_dir / "generation_report.json"
    action_counts = Counter(
        (task["split"], task["frozen_policy_decision"]["action"])
        for task in tasks
    )
    report = {
        "schema_version": "1.0",
        "dataset_id": tasks_doc["dataset_id"],
        "status": "passed",
        "task_count": len(tasks),
        "task_count_by_tool": dict(
            sorted(Counter(task["source_tool_id"] for task in tasks).items())
        ),
        "task_count_by_split": tasks_doc["task_count_by_split"],
        "policy_action_count_by_split": {
            f"{split}::{action}": count
            for (split, action), count in sorted(action_counts.items())
        },
        "e1b_group_overlap_count": 0,
        "a003_precision_pair_count": len(
            {
                task["base_task_group_id"]
                for task in tasks
                if task["source_tool_id"] == "A003"
            }
        ),
        "experimental_condition_count": len(EXPERIMENTAL_CONDITIONS),
        "api_model_runs_performed": False,
        "evaluation_split_opened": False,
        "reference_generation": {
            "production_tool_code_imported": False,
            "basis": "frozen seed facts plus independent elementary equations",
        },
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    write_json(report_path, report)

    manifest_path = output_dir / "artifact_manifest.json"
    manifest = {
        "schema_version": "1.0",
        "dataset_id": tasks_doc["dataset_id"],
        "artifacts": [
            {"filename": tasks_path.name, "sha256": file_hash(tasks_path)},
            {"filename": report_path.name, "sha256": file_hash(report_path)},
        ],
        "source_artifacts": [
            {
                "filename": project_relative(HERE / "protocol_v1.md"),
                "sha256": file_hash(HERE / "protocol_v1.md"),
            },
            {
                "filename": project_relative(seeds_path),
                "sha256": file_hash(seeds_path),
            },
            {
                "filename": project_relative(contracts_path),
                "sha256": file_hash(contracts_path),
            },
            {
                "filename": project_relative(policy_path),
                "sha256": file_hash(policy_path),
            },
            {
                "filename": project_relative(e1b_tasks_path),
                "sha256": file_hash(e1b_tasks_path),
            },
        ],
        "evaluation_split_opened": False,
        "core_frozen": False,
    }
    write_json(manifest_path, manifest)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seeds",
        type=Path,
        default=HERE / "task_seeds_v1.json",
    )
    parser.add_argument(
        "--contracts",
        type=Path,
        default=HERE.parent / "verified_core" / "contracts_v1.json",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=HERE.parent / "e1b_v2" / "candidate_gate_policy_v1.json",
    )
    parser.add_argument(
        "--e1b-tasks",
        type=Path,
        default=(
            PROJECT_ROOT
            / "outputs"
            / "e1b_taskset_v2_20260730"
            / "e1b_tasks_v2.json"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "e1c_taskset_v1_20260731",
    )
    args = parser.parse_args()
    report = generate(
        args.seeds,
        args.contracts,
        args.policy,
        args.e1b_tasks,
        args.output_dir,
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
