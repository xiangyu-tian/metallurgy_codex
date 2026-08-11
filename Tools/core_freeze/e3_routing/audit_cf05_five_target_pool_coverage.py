"""Audit deterministic 0/4/8 pool coverage for the five verified E3 targets."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common  # noqa: E402


CONFIG_PATH = Path(__file__).with_name("cf05_five_target_pool_coverage_audit_config_v1.json")


def validate_config(config: dict[str, Any]) -> None:
    if config["target_tool_ids"] != ["A001", "A002", "A003", "A004", "B019"]:
        raise ValueError("five-target audit scope changed")
    if config["required_pool_sizes"] != [17, 50, 100, 120]:
        raise ValueError("required pool sizes changed")
    if config["required_pool_repeats"] != ["A", "B", "C", "D", "E"]:
        raise ValueError("required pool repeats changed")
    expected_conditions = [
        {"near_neighbor_type": "none", "near_neighbor_count": 0},
        {"near_neighbor_type": "lexical", "near_neighbor_count": 4},
        {"near_neighbor_type": "lexical", "near_neighbor_count": 8},
        {"near_neighbor_type": "functional_overlap", "near_neighbor_count": 4},
        {"near_neighbor_type": "functional_overlap", "near_neighbor_count": 8},
    ]
    if config["required_conditions"] != expected_conditions:
        raise ValueError("required controlled conditions changed")
    for field in (
        "external_api_calls_authorized",
        "new_tool_identity_creation_allowed",
        "independent_validation_split_access_allowed",
        "confirmatory_inference_allowed",
        "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")
    if config["cf05_status"] != "in_progress":
        raise ValueError("coverage audit cannot pass CF-05")


def _condition_key(row: dict[str, Any]) -> tuple[str, int]:
    neighbor_type = row["near_neighbor_type"]
    if neighbor_type == "contract_mismatch":
        neighbor_type = "functional_overlap"
    return neighbor_type, int(row["near_neighbor_count"])


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {
        name: common.validate_binding(binding)
        for name, binding in config["bindings"].items()
    }
    sources = {name: common.load_json(path) for name, path in paths.items()}
    adoption = sources["method_freeze_adoption"]
    if adoption["decision"] != "adopted":
        raise ValueError("method freeze has not been adopted")

    required_conditions = {
        (row["near_neighbor_type"], row["near_neighbor_count"])
        for row in config["required_conditions"]
    }
    expected_combinations = {
        (size, repeat, condition[0], condition[1])
        for size in config["required_pool_sizes"]
        for repeat in config["required_pool_repeats"]
        for condition in required_conditions
    }
    required_records_per_target = len(expected_combinations)
    if required_records_per_target != 100:
        raise ValueError("strict target grid must contain 100 pool records")

    a003_records = sources["a003_controlled_pool_manifest"]["records"]
    a003_combinations = {
        (
            int(row["tool_pool_size"]),
            row["pool_repeat"],
            *_condition_key(row),
        )
        for row in a003_records
    }
    if len(a003_records) != 100 or a003_combinations != expected_combinations:
        raise ValueError("A003 controlled grid is no longer complete")
    if sources["a003_pool_audit"].get("all_pool_invariants_passed") is not True:
        raise ValueError("A003 pool audit is not passed")

    a004_pools = sources["a004_controlled_pools"]["pools"]
    if len(a004_pools) != 6:
        raise ValueError("A004 partial controlled grid changed")
    a004_conditions = Counter(
        (int(row["tool_pool_size"]), *_condition_key(row)) for row in a004_pools
    )
    expected_a004 = Counter(
        {
            (17, "none", 0): 1,
            (120, "none", 0): 1,
            (17, "lexical", 4): 1,
            (120, "lexical", 4): 1,
            (17, "functional_overlap", 4): 1,
            (120, "functional_overlap", 4): 1,
        }
    )
    if a004_conditions != expected_a004:
        raise ValueError("A004 partial pool evidence changed")

    readiness_rows = {
        row["target_tool_id"]: row
        for row in sources["older_readiness_matrix"]["rows"]
    }
    if set(readiness_rows) != set(config["target_tool_ids"]):
        raise ValueError("older readiness target set changed")
    task_gold = sources["multitarget_task_gold_report"]
    if (
        task_gold["status"]
        != "non_a003_task_gold_candidate_revalidated_for_development_scope"
        or task_gold["target_count"] != 4
        or task_gold["unexpected_execution_failure_task_ids"]
    ):
        raise ValueError("multi-target development gold evidence changed")

    relation_counts = Counter(
        (row["target_tool_id"], row["relation_type"])
        for row in sources["combined_relation_registry"]["relations"]
        if row.get("relation_registry_admitted") is True
    )
    effective_counts = {
        target: {
            "lexical": int(readiness_rows[target]["lexical_neighbor_count"]),
            "functional_overlap": int(
                readiness_rows[target]["contract_mismatch_neighbor_count"]
            ),
        }
        for target in config["target_tool_ids"]
    }
    effective_counts["A003"] = {"lexical": 8, "functional_overlap": 8}
    effective_counts["A004"] = {"lexical": 4, "functional_overlap": 4}

    existing_pool_records = {"A001": 0, "A002": 0, "A003": 100, "A004": 6, "B019": 0}
    rows = []
    for target in config["target_tool_ids"]:
        lexical = effective_counts[target]["lexical"]
        functional = effective_counts[target]["functional_overlap"]
        records = existing_pool_records[target]
        rows.append(
            {
                "target_tool_id": target,
                "development_task_gold_ready": True,
                "effective_lexical_neighbor_count": lexical,
                "effective_functional_neighbor_count": functional,
                "admitted_registry_lexical_count": relation_counts[(target, "lexical")],
                "admitted_registry_contract_mismatch_count": relation_counts[
                    (target, "contract_mismatch")
                ],
                "lexical_gap_to_4": max(0, 4 - lexical),
                "functional_gap_to_4": max(0, 4 - functional),
                "lexical_gap_to_8": max(0, 8 - lexical),
                "functional_gap_to_8": max(0, 8 - functional),
                "dose_4_neighbor_evidence_ready": lexical >= 4 and functional >= 4,
                "dose_8_neighbor_evidence_ready": lexical >= 8 and functional >= 8,
                "existing_controlled_pool_record_count": records,
                "required_strict_pool_record_count": required_records_per_target,
                "missing_strict_pool_record_count": required_records_per_target - records,
                "strict_0_4_8_grid_complete": records == required_records_per_target,
                "coverage_status": (
                    "complete"
                    if records == required_records_per_target
                    else "partial"
                    if records
                    else "not_constructed"
                ),
            }
        )

    gap_to_4 = sum(
        row["lexical_gap_to_4"] + row["functional_gap_to_4"] for row in rows
    )
    gap_to_8 = sum(
        row["lexical_gap_to_8"] + row["functional_gap_to_8"] for row in rows
    )
    report = {
        "schema_version": "1.0",
        "audit_id": config["audit_id"],
        "status": "five_target_coverage_audited_incomplete",
        "target_count": len(rows),
        "strict_grid_complete_target_count": sum(
            row["strict_0_4_8_grid_complete"] for row in rows
        ),
        "strict_grid_complete_target_ids": [
            row["target_tool_id"] for row in rows if row["strict_0_4_8_grid_complete"]
        ],
        "dose_4_neighbor_ready_target_ids": [
            row["target_tool_id"] for row in rows if row["dose_4_neighbor_evidence_ready"]
        ],
        "dose_8_neighbor_ready_target_ids": [
            row["target_tool_id"] for row in rows if row["dose_8_neighbor_evidence_ready"]
        ],
        "existing_controlled_pool_record_count": sum(
            row["existing_controlled_pool_record_count"] for row in rows
        ),
        "required_strict_pool_record_count": required_records_per_target * len(rows),
        "missing_strict_pool_record_count": sum(
            row["missing_strict_pool_record_count"] for row in rows
        ),
        "neighbor_slot_gap_to_paired_4": gap_to_4,
        "neighbor_slot_gap_to_paired_8": gap_to_8,
        "task_gold_ready_target_count": sum(
            row["development_task_gold_ready"] for row in rows
        ),
        "external_api_calls": 0,
        "new_tool_identities_created": 0,
        "independent_validation_split_accessed": False,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "conclusion": "A003 is the only target with the complete strict 0/4/8 grid. A004 has dose-4 neighbor evidence and six partial 17/120 pools. A001, A002, and B019 require additional relation evidence before deterministic full pool construction.",
        "next_gate": "freeze a staged relation-evidence expansion plan; do not construct formal pools from weak or invented neighbors",
    }
    expansion_queue = [
        {
            "priority_rank": rank,
            "target_tool_id": target,
            "immediate_goal": goal,
            "required_action": action,
            "external_api_required": False,
        }
        for rank, (target, goal, action) in enumerate(
            [
                (
                    "A004",
                    "complete 17/50/100/120 A-E dose-0/4 pool replication, then add four lexical and four functional neighbors for dose 8",
                    "reuse existing dose-4 evidence for deterministic pool replication; separately source and validate dose-8 relations",
                ),
                (
                    "B019",
                    "add four functional neighbors for paired dose 4 before dose 8",
                    "source contract-mismatch candidates with executable negative applicability evidence",
                ),
                (
                    "A002",
                    "add one lexical and three functional neighbors for paired dose 4",
                    "extend relation evidence without treating acceptable equivalent E3C002 as a distractor",
                ),
                (
                    "A001",
                    "add four lexical and three functional neighbors for paired dose 4",
                    "source independent conversion-related candidates and validate target/candidate boundary fixtures",
                ),
            ],
            start=1,
        )
    ]
    return {"rows": rows, "report": report, "expansion_queue": expansion_queue}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = common.load_json(CONFIG_PATH)
    result = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "cf05_five_target_pool_coverage_config_snapshot.json": config,
        "cf05_five_target_pool_coverage_matrix.json": {
            "schema_version": "1.0",
            "rows": result["rows"],
        },
        "cf05_relation_expansion_queue.json": {
            "schema_version": "1.0",
            "rows": result["expansion_queue"],
        },
        "cf05_five_target_pool_coverage_report.json": result["report"],
    }
    for filename, value in artifacts.items():
        common.write_json(output_dir / filename, value)
    write_csv(output_dir / "cf05_five_target_pool_coverage_matrix.csv", result["rows"])
    paths = sorted(output_dir.iterdir(), key=lambda path: path.name)
    common.write_json(
        output_dir / "artifact_manifest.json",
        {
            "schema_version": "1.0",
            "audit_id": config["audit_id"],
            "artifact_count": len(paths),
            "artifacts": [
                {
                    "filename": path.name,
                    "sha256": common.file_hash(path),
                    "bytes": path.stat().st_size,
                }
                for path in paths
            ],
        },
    )
    return result["report"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else WORKSPACE / args.output_dir
    print(json.dumps(build_outputs(output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
