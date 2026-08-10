"""Build a hash-bound readiness audit for expanding E3 beyond A003.

The audit is deliberately offline.  It distinguishes reusable task/reference
evidence from target-specific gold and neighbor evidence, and it refuses to
interpret an available task as an execution-ready routing experiment.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("multitarget_readiness_config_v1.json")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validate_binding(binding: dict[str, str]) -> Path:
    path = WORKSPACE / binding["path"]
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256_file(path)
    if actual != binding["sha256"].lower():
        raise ValueError(f"bound file hash mismatch for {path}: {actual}")
    return path


def validate_policy(config: dict[str, Any]) -> None:
    if config["confirmatory_use_allowed"]:
        raise ValueError("confirmatory_use_allowed must remain false")
    if config["external_api_calls_authorized"]:
        raise ValueError("external_api_calls_authorized must remain false")
    if config["core_frozen"]:
        raise ValueError("core_frozen must remain false")
    if config["near_neighbor_doses"] != [0, 4, 8]:
        raise ValueError("near_neighbor_doses must remain [0, 4, 8]")


def task_inventory(tasks: list[dict[str, Any]], target_id: str) -> dict[str, Any]:
    rows = [row for row in tasks if row["source_tool_id"] == target_id]
    independent_rows = [
        row
        for row in rows
        if row.get("reference_execution", {}).get("production_code_imported") is False
        and row.get("reference_execution", {}).get("oracle_basis")
    ]
    singleton_target_rows = [
        row for row in rows if row.get("acceptable_tools") == [target_id]
    ]
    return {
        "target_tool_id": target_id,
        "task_count": len(rows),
        "task_ids": [row["task_id"] for row in rows],
        "base_task_group_count": len({row["base_task_group_id"] for row in rows}),
        "base_task_group_ids": sorted({row["base_task_group_id"] for row in rows}),
        "precision_policies": sorted({row["precision_policy"] for row in rows}),
        "independent_reference_task_count": len(independent_rows),
        "all_tasks_have_independent_reference": len(independent_rows) == len(rows),
        "baseline_singleton_target_acceptable_set_count": len(singleton_target_rows),
        "baseline_taskset_acceptable_sets_are_not_expanded_registry_revalidation": True,
    }


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_policy(config)
    bound_paths = {
        name: validate_binding(binding)
        for name, binding in config["bindings"].items()
    }
    task_document = load_json(bound_paths["development_taskset"])
    gap_document = load_json(bound_paths["current_gap_matrix"])
    relation_document = load_json(bound_paths["relation_evidence_registry"])
    a003_gold = load_json(bound_paths["a003_task_gold_report"])
    a003_pool = load_json(bound_paths["a003_pool_report"])
    a003_analysis = load_json(bound_paths["a003_development_analysis"])

    target_ids = config["target_tool_ids"]
    if sorted({row["source_tool_id"] for row in task_document["tasks"]}) != sorted(target_ids):
        raise ValueError("taskset target IDs do not match configured target IDs")
    gap_by_target = {row["target_tool_id"]: row for row in gap_document["rows"]}
    if set(gap_by_target) != set(target_ids):
        raise ValueError("gap matrix target IDs do not match configured target IDs")
    if relation_document["relation_count"] != len(relation_document["relations"]):
        raise ValueError("relation registry count does not match relation rows")
    if a003_gold["target_tool_id"] != "A003" or a003_gold["task_count"] != 12:
        raise ValueError("unexpected A003 task-gold evidence")
    if a003_pool["target_tool_id"] != "A003" or not a003_pool["all_pool_invariants_passed"]:
        raise ValueError("unexpected A003 pool evidence")
    if a003_analysis["overall"]["complete_call_accuracy"] != 1.0:
        raise ValueError("the bound A003 ceiling-effect result changed")

    inventories = {
        target_id: task_inventory(task_document["tasks"], target_id)
        for target_id in target_ids
    }
    task_gold_ids = set(config["task_gold_revalidated_target_ids"])
    pool_ids = set(config["controlled_pool_constructed_target_ids"])
    completed_ids = set(config["completed_development_target_ids"])
    readiness_rows = []
    for target_id in target_ids:
        gap = gap_by_target[target_id]
        inventory = inventories[target_id]
        lexical_count = gap["lexical_count_after"]
        contract_count = gap["contract_mismatch_count_after"]
        task_source_ready = (
            inventory["task_count"] >= config["minimum_development_tasks_per_target"]
            and inventory["all_tasks_have_independent_reference"]
        )
        gold_ready = target_id in task_gold_ids
        pool_ready = target_id in pool_ids
        paired4_ready = lexical_count >= 4 and contract_count >= 4
        paired8_ready = lexical_count >= 8 and contract_count >= 8
        readiness_rows.append(
            {
                "target_tool_id": target_id,
                "task_count": inventory["task_count"],
                "base_task_group_count": inventory["base_task_group_count"],
                "task_source_and_independent_reference_ready": task_source_ready,
                "expanded_registry_task_gold_revalidated": gold_ready,
                "lexical_neighbor_count": lexical_count,
                "contract_mismatch_neighbor_count": contract_count,
                "lexical_gap_to_4": max(0, 4 - lexical_count),
                "contract_mismatch_gap_to_4": max(0, 4 - contract_count),
                "lexical_gap_to_8": max(0, 8 - lexical_count),
                "contract_mismatch_gap_to_8": max(0, 8 - contract_count),
                "paired_4_ready": paired4_ready,
                "paired_8_ready": paired8_ready,
                "controlled_pool_constructed": pool_ready,
                "development_run_completed": target_id in completed_ids,
                "mixed_realistic_opening_ready": task_source_ready and gold_ready,
                "controlled_dose_opening_ready": (
                    task_source_ready and gold_ready and paired8_ready and pool_ready
                ),
            }
        )

    pending_rows = [row for row in readiness_rows if not row["development_run_completed"]]
    expansion_rows = []
    for row in pending_rows:
        gap4_total = row["lexical_gap_to_4"] + row["contract_mismatch_gap_to_4"]
        gap8_total = row["lexical_gap_to_8"] + row["contract_mismatch_gap_to_8"]
        expansion_rows.append(
            {
                "target_tool_id": row["target_tool_id"],
                "missing_slots_to_paired_4": gap4_total,
                "missing_slots_to_paired_8": gap8_total,
                "lexical_gap_to_4": row["lexical_gap_to_4"],
                "contract_mismatch_gap_to_4": row["contract_mismatch_gap_to_4"],
                "lexical_gap_to_8": row["lexical_gap_to_8"],
                "contract_mismatch_gap_to_8": row["contract_mismatch_gap_to_8"],
                "first_required_gate": (
                    "task_gold_revalidation"
                    if not row["expanded_registry_task_gold_revalidated"]
                    else "neighbor_evidence_expansion"
                ),
            }
        )
    expansion_rows.sort(
        key=lambda row: (
            row["missing_slots_to_paired_4"],
            -gap_by_target[row["target_tool_id"]]["lexical_count_after"],
            row["target_tool_id"],
        )
    )
    for index, row in enumerate(expansion_rows, start=1):
        row["priority_rank"] = index

    non_a003_task_count = sum(
        inventories[target_id]["task_count"]
        for target_id in target_ids
        if target_id != "A003"
    )
    report = {
        "schema_version": "1.0",
        "audit_id": config["audit_id"],
        "status": "multitarget_inputs_audited_expansion_required",
        "target_count": len(target_ids),
        "task_count": len(task_document["tasks"]),
        "non_a003_task_count_requiring_expanded_registry_gold_revalidation": non_a003_task_count,
        "task_source_ready_target_count": sum(
            row["task_source_and_independent_reference_ready"] for row in readiness_rows
        ),
        "task_gold_revalidated_target_count": sum(
            row["expanded_registry_task_gold_revalidated"] for row in readiness_rows
        ),
        "paired_4_ready_target_ids": [
            row["target_tool_id"] for row in readiness_rows if row["paired_4_ready"]
        ],
        "paired_8_ready_target_ids": [
            row["target_tool_id"] for row in readiness_rows if row["paired_8_ready"]
        ],
        "completed_development_target_ids": sorted(completed_ids),
        "a003_ceiling_effect_observed": True,
        "a003_complete_call_accuracy": a003_analysis["overall"]["complete_call_accuracy"],
        "recommended_immediate_work": [
            "revalidate expanded-registry task-level acceptable sets for the 33 non-A003 development tasks",
            "prepare a no-API mixed-realistic 17/120 multi-target opening after task-gold revalidation",
            "expand near-neighbor evidence in the recorded priority order, starting with A004",
        ],
        "external_api_calls": 0,
        "external_api_calls_authorized": False,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
    }
    return {
        "task_inventory": {
            "audit_id": config["audit_id"],
            "source_dataset_id": task_document["dataset_id"],
            "targets": [inventories[target_id] for target_id in target_ids],
        },
        "readiness_matrix": {
            "audit_id": config["audit_id"],
            "rows": readiness_rows,
        },
        "expansion_queue": {
            "audit_id": config["audit_id"],
            "priority_policy": config["expansion_priority_policy"],
            "rows": expansion_rows,
            "weak_neighbor_fill_allowed": False,
            "formal_pool_generation_allowed": False,
        },
        "report": report,
    }


CSV_FIELDS = [
    "target_tool_id",
    "task_count",
    "base_task_group_count",
    "task_source_and_independent_reference_ready",
    "expanded_registry_task_gold_revalidated",
    "lexical_neighbor_count",
    "contract_mismatch_neighbor_count",
    "lexical_gap_to_4",
    "contract_mismatch_gap_to_4",
    "lexical_gap_to_8",
    "contract_mismatch_gap_to_8",
    "paired_4_ready",
    "paired_8_ready",
    "controlled_pool_constructed",
    "development_run_completed",
    "mixed_realistic_opening_ready",
    "controlled_dose_opening_ready",
]


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    result = build(config)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_outputs = {
        "multitarget_task_inventory.json": result["task_inventory"],
        "target_readiness_matrix.json": result["readiness_matrix"],
        "neighbor_expansion_queue.json": result["expansion_queue"],
        "multitarget_readiness_report.json": result["report"],
        "multitarget_readiness_config_snapshot.json": config,
    }
    for filename, value in json_outputs.items():
        write_json(output_dir / filename, value)
    csv_path = output_dir / "target_readiness_matrix.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(result["readiness_matrix"]["rows"])

    artifact_names = [*json_outputs, csv_path.name]
    manifest = {
        "audit_id": config["audit_id"],
        "artifact_count": len(artifact_names),
        "artifacts": [
            {
                "filename": filename,
                "sha256": sha256_file(output_dir / filename),
                "bytes": (output_dir / filename).stat().st_size,
            }
            for filename in artifact_names
        ],
    }
    write_json(output_dir / "artifact_manifest.json", manifest)
    return result["report"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = build_outputs(args.output_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
