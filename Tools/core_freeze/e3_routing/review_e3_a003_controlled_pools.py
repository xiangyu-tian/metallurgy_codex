"""Independently review A003 controlled pools and task-gold freshness.

This module deliberately does not import the pool builder.  It recomputes the
design grid, neighbor-type separation, runtime-evidence coverage, and nested
pool invariants from frozen artifacts.  It also prevents a structurally valid
pool from being used with an obsolete task-level acceptable-tool set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("a003_independent_review_config_v1.json")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_binding(binding: dict[str, str]) -> Path:
    path = WORKSPACE / binding["path"]
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256_file(path)
    if actual != binding["sha256"].lower():
        raise ValueError(f"bound file hash mismatch for {path}: {actual}")
    return path


def rows_from(value: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("rows", "relations", "records", "candidates"):
        rows = value.get(key)
        if isinstance(rows, list):
            return rows
    raise ValueError("bound JSON does not contain a supported row collection")


def evidence_index(sources: dict[str, Any], target_id: str) -> dict[str, dict[str, Any]]:
    target = next(
        row
        for row in sources["neighbor_matrix"]["targets"]
        if row["target_tool_id"] == target_id
    )
    rows = list(target["lexical_candidates"])
    for key in (
        "relation_evidence_batch1",
        "relation_evidence_batch2",
        "relation_evidence_batch3",
    ):
        rows.extend(
            row
            for row in rows_from(sources[key])
            if row["target_tool_id"] == target_id
        )
    indexed = {row["candidate_tool_id"]: row for row in rows}
    if len(indexed) != len(rows):
        duplicates = sorted(
            tool_id
            for tool_id in indexed
            if sum(row["candidate_tool_id"] == tool_id for row in rows) > 1
        )
        raise ValueError(f"duplicate relation evidence rows: {duplicates}")
    return indexed


def runtime_index(sources: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for key in (
        "runtime_results_batch1",
        "runtime_results_batch2",
        "runtime_results_batch3",
    ):
        for row in rows_from(sources[key]):
            indexed[row["candidate_tool_id"]].append(row)
    return dict(indexed)


def review_relations(
    config: dict[str, Any], sources: dict[str, Any]
) -> list[dict[str, Any]]:
    assignment = sources["neighbor_assignment"]
    lexical_ids = assignment["lexical_neighbor_ids"]
    mismatch_ids = assignment["functional_overlap_interface_neighbor_ids"]
    if lexical_ids != config["expected_lexical_neighbor_ids"]:
        raise ValueError("lexical neighbor assignment changed")
    if mismatch_ids != config["expected_contract_mismatch_neighbor_ids"]:
        raise ValueError("contract-mismatch neighbor assignment changed")
    if set(lexical_ids) & set(mismatch_ids):
        raise ValueError("neighbor categories overlap")

    admitted = {
        (row["candidate_tool_id"], row["relation_type"]): row
        for row in sources["combined_relations"]["relations"]
        if row["target_tool_id"] == config["target_tool_id"]
        and row.get("relation_registry_admitted") is True
    }
    evidence = evidence_index(sources, config["target_tool_id"])
    runtime = runtime_index(sources)
    review_rows: list[dict[str, Any]] = []

    for relation_type, ids in (
        ("lexical", lexical_ids),
        ("contract_mismatch", mismatch_ids),
    ):
        for tool_id in ids:
            row = evidence.get(tool_id)
            if row is None:
                raise ValueError(f"missing independent evidence row for {tool_id}")
            if (tool_id, relation_type) not in admitted and tool_id.startswith("E3C"):
                raise ValueError(f"missing admitted relation for {tool_id}")
            if relation_type == "lexical":
                checks = {
                    "algorithmic_lexical_candidate": row.get("algorithmic_lexical_candidate") is True,
                    "different_core_method": row.get("same_core_method") is False,
                }
            else:
                checks = {
                    "same_scenario": row.get("same_scenario") is True,
                    "same_core_method": row.get("same_core_method") is True,
                    "not_algorithmic_lexical": row.get("algorithmic_lexical_candidate") is False,
                    "provable_contract_mismatch": row.get("provable_contract_mismatch_neighbor") is True,
                    "relation_evidence_passed": row.get("relation_evidence_passed") is True,
                }
            if not all(checks.values()):
                raise ValueError(f"relation separation failed for {tool_id}: {checks}")

            runtime_checks: dict[str, bool | int | None]
            if tool_id.startswith("E3C"):
                cases = runtime.get(tool_id, [])
                runtime_checks = {
                    "case_count": len(cases),
                    "all_contract_outcomes_passed": bool(cases)
                    and all(case.get("contract_outcome_pass") is True for case in cases),
                    "success_case_present": any(
                        case.get("execution", {}).get("success") is True for case in cases
                    ),
                    "failure_case_present": any(
                        case.get("execution", {}).get("success") is False for case in cases
                    ),
                }
                if not all(
                    value
                    for key, value in runtime_checks.items()
                    if key != "case_count"
                ):
                    raise ValueError(f"runtime evidence incomplete for {tool_id}: {runtime_checks}")
            else:
                runtime_checks = {
                    "case_count": None,
                    "all_contract_outcomes_passed": None,
                    "success_case_present": None,
                    "failure_case_present": None,
                }
            review_rows.append(
                {
                    "target_tool_id": config["target_tool_id"],
                    "candidate_tool_id": tool_id,
                    "relation_type": relation_type,
                    "relation_checks": checks,
                    "runtime_checks": runtime_checks,
                    "review_passed": True,
                }
            )
    return review_rows


def review_pool_grid(config: dict[str, Any], sources: dict[str, Any]) -> dict[str, Any]:
    records = sources["pool_manifest"]["records"]
    expected_grid = {
        (repeat, size, condition[0], condition[1], condition[2])
        for repeat in config["expected_pool_repeats"]
        for size in config["expected_pool_sizes"]
        for condition in config["expected_conditions"]
    }
    observed_grid = {
        (
            row["pool_repeat"],
            row["tool_pool_size"],
            row["near_neighbor_type"],
            row["near_neighbor_count"],
            row["evidence_relation_type"],
        )
        for row in records
    }
    if observed_grid != expected_grid or len(records) != len(expected_grid):
        raise ValueError("controlled pool design grid mismatch")

    assigned = set(config["expected_lexical_neighbor_ids"]) | set(
        config["expected_contract_mismatch_neighbor_ids"]
    )
    pool_ids: set[str] = set()
    for row in records:
        if row["pool_id"] in pool_ids:
            raise ValueError(f"duplicate pool_id: {row['pool_id']}")
        pool_ids.add(row["pool_id"])
        order = row["tool_order"]
        if len(order) != row["tool_pool_size"] or len(set(order)) != len(order):
            raise ValueError(f"pool size or uniqueness failed: {row['pool_id']}")
        if order.count(config["target_tool_id"]) != 1:
            raise ValueError(f"target multiplicity failed: {row['pool_id']}")
        if set(order) & assigned != set(row["near_neighbor_tool_ids"]):
            raise ValueError(f"neighbor leakage failed: {row['pool_id']}")
        if len(row["near_neighbor_tool_ids"]) != row["near_neighbor_count"]:
            raise ValueError(f"neighbor dose failed: {row['pool_id']}")

    for repeat in config["expected_pool_repeats"]:
        for size in config["expected_pool_sizes"]:
            for count in (4, 8):
                pair = [
                    row
                    for row in records
                    if row["pool_repeat"] == repeat
                    and row["tool_pool_size"] == size
                    and row["near_neighbor_count"] == count
                ]
                if len(pair) != 2:
                    raise ValueError("paired condition missing")
                if pair[0]["neutral_tool_ids"] != pair[1]["neutral_tool_ids"]:
                    raise ValueError("paired neutral base mismatch")
                if pair[0]["neighbor_slot_positions_1_based"] != pair[1][
                    "neighbor_slot_positions_1_based"
                ]:
                    raise ValueError("paired neighbor slots mismatch")

        for condition in config["expected_conditions"]:
            rows = sorted(
                (
                    row
                    for row in records
                    if row["pool_repeat"] == repeat
                    and row["near_neighbor_type"] == condition[0]
                    and row["near_neighbor_count"] == condition[1]
                ),
                key=lambda row: row["tool_pool_size"],
            )
            for left, right in zip(rows, rows[1:]):
                if not set(left["tool_order"]).issubset(right["tool_order"]):
                    raise ValueError("pool nesting failed")

    if sources["pool_audit"].get("all_pool_invariants_passed") is not True:
        raise ValueError("builder audit did not pass")
    return {
        "record_count": len(records),
        "expected_grid_cell_count": len(expected_grid),
        "pool_id_unique": True,
        "target_present_once": True,
        "exact_neighbor_dose": True,
        "neighbor_categories_disjoint": True,
        "paired_neutral_bases_match": True,
        "paired_neighbor_slots_match": True,
        "nested_across_sizes": True,
        "independent_pool_review_passed": True,
    }


def review_task_gold(config: dict[str, Any], sources: dict[str, Any]) -> dict[str, Any]:
    tasks = [
        row
        for row in sources["a003_taskset"]["tasks"]
        if row.get("source_tool_id") == config["target_tool_id"]
    ]
    if not tasks:
        raise ValueError("no bound A003 tasks found")
    stale = [
        row["task_id"]
        for row in tasks
        if row.get("acceptable_tools") == [config["target_tool_id"]]
    ]
    registry = {
        row["candidate_tool_id"]: row
        for row in sources["candidate_registry_batch1"]["candidates"]
    }
    direct_overlap = []
    for tool_id in config["known_direct_contract_overlap_ids"]:
        row = registry[tool_id]
        function = row["openai_tool"]["function"]
        direct_overlap.append(
            {
                "candidate_tool_id": tool_id,
                "required_parameters": function["parameters"].get("required", []),
                "main_output": row["main_output"],
                "same_target_input_key": function["parameters"].get("required") == ["formula"],
                "target_quantity_output": row["main_output"] == "摩尔质量",
            }
        )
    if not all(
        row["same_target_input_key"] and row["target_quantity_output"]
        for row in direct_overlap
    ):
        raise ValueError("configured direct contract overlap is not reproducible")
    return {
        "bound_a003_task_count": len(tasks),
        "task_ids_with_singleton_acceptable_tools": stale,
        "singleton_acceptable_tool_count": len(stale),
        "new_direct_contract_overlap_candidates": direct_overlap,
        "acceptable_tool_set_revalidation_required": bool(stale and direct_overlap),
        "reason": (
            "The task gold predates admitted candidates. At least one candidate has "
            "the same direct formula input and molar-mass output contract, so task-level "
            "numeric tolerance must be re-evaluated before routing accuracy is scored."
        ),
    }


def build(config: dict[str, Any]) -> dict[str, Any]:
    for field in (
        "development_routing_run_allowed",
        "confirmatory_use_allowed",
        "external_api_calls_authorized",
        "core_frozen",
    ):
        if config.get(field) is not False:
            raise ValueError(f"{field} must remain false in the independent review")
    paths = {name: validate_binding(binding) for name, binding in config["bindings"].items()}
    sources = {name: load_json(path) for name, path in paths.items()}
    relation_rows = review_relations(config, sources)
    pool_review = review_pool_grid(config, sources)
    task_gold = review_task_gold(config, sources)
    if not task_gold["acceptable_tool_set_revalidation_required"]:
        raise ValueError("expected task-gold freshness gate did not trigger")
    report = {
        "review_id": config["review_id"],
        "status": "pool_and_relation_review_passed_task_gold_revalidation_required",
        "target_tool_id": config["target_tool_id"],
        "pool_structure_review": "passed",
        "relation_separation_review": "passed",
        "runtime_evidence_review": "passed",
        "relation_review_count": len(relation_rows),
        "lexical_relation_count": sum(row["relation_type"] == "lexical" for row in relation_rows),
        "contract_mismatch_relation_count": sum(
            row["relation_type"] == "contract_mismatch" for row in relation_rows
        ),
        "task_acceptable_set_review": "stale_revalidation_required",
        "development_routing_run_allowed": False,
        "confirmatory_use_allowed": False,
        "external_api_calls": 0,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "next_gate": "recompute A003 task-level acceptable tool sets against admitted candidates before any routing run",
    }
    return {
        "report": report,
        "relation_rows": relation_rows,
        "pool_review": pool_review,
        "task_gold": task_gold,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    result = build(config)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "a003_independent_review_config_snapshot.json": config,
        "a003_independent_review_report.json": result["report"],
        "a003_relation_review_rows.json": {"rows": result["relation_rows"]},
        "a003_pool_independent_audit.json": result["pool_review"],
        "a003_task_gold_freshness_audit.json": result["task_gold"],
    }
    paths = []
    for filename, value in artifacts.items():
        path = output_dir / filename
        write_json(path, value)
        paths.append(path)
    manifest = {
        "review_id": config["review_id"],
        "artifact_count": len(paths),
        "artifacts": [
            {
                "filename": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in sorted(paths)
        ],
    }
    write_json(output_dir / "artifact_manifest.json", manifest)
    return result["report"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    report = build_outputs(args.output_dir.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
