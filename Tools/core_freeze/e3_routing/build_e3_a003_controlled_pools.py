"""Build nonformal A003 controlled-dose routing pools without API calls.

The legacy statistical interface calls the high-similarity condition
``functional_overlap``.  This builder does not silently claim expert semantic
validation: its high-similarity neighbors are contract-derived mismatch
proxies, and every artifact records that limitation.  The resulting pools are
development evidence only until the protocol's formal-use requirements are
satisfied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from Tools.core_freeze.e3_routing.audit_e3_neighbor_feasibility import (
    score_pair,
    structured_contract,
)


CONFIG_PATH = Path(__file__).with_name("a003_controlled_pool_config_v1.json")
EXPECTED_POOL_SIZES = [17, 50, 100, 120]
EXPECTED_POOL_REPEATS = ["A", "B", "C", "D", "E"]
EXPECTED_CONDITIONS = [
    ("none", 0, "none"),
    ("lexical", 4, "lexical"),
    ("lexical", 8, "lexical"),
    ("functional_overlap", 4, "contract_mismatch"),
    ("functional_overlap", 8, "contract_mismatch"),
]


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


def validate_bound_file(binding: dict[str, str]) -> Path:
    path = WORKSPACE / binding["path"]
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256_file(path)
    if actual != binding["sha256"].lower():
        raise ValueError(f"bound file hash mismatch for {path}: {actual}")
    return path


def ranked(values: list[Any], seed: str, *parts: object) -> list[Any]:
    prefix = "|".join([seed, *(str(part) for part in parts)])
    return sorted(
        values,
        key=lambda value: (
            hashlib.sha256(f"{prefix}|{value}".encode("utf-8")).hexdigest(),
            str(value),
        ),
    )


def normalize_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(candidate)
    normalized.setdefault("tool_id", normalized["candidate_tool_id"])
    return normalized


def condition_key(condition: dict[str, Any]) -> str:
    return f"{condition['near_neighbor_type']}_{condition['near_neighbor_count']}"


def load_sources(config: dict[str, Any]) -> dict[str, Any]:
    paths = {
        name: validate_bound_file(binding)
        for name, binding in config["bindings"].items()
    }
    catalog = load_json(paths["catalog"])
    base_pools = load_json(paths["base_pool_manifest"])
    neighbor_matrix = load_json(paths["neighbor_matrix"])
    relations = load_json(paths["combined_relation_registry"])
    contracts = load_json(paths["verified_contracts"])
    audit_config = load_json(paths["neighbor_audit_config"])

    candidate_rows: list[dict[str, Any]] = []
    for name in (
        "candidate_registry_batch1",
        "candidate_registry_batch2",
        "candidate_registry_batch3",
    ):
        candidate_rows.extend(
            normalize_candidate(row)
            for row in load_json(paths[name])["candidates"]
        )
    candidate_by_id = {row["tool_id"]: row for row in candidate_rows}
    if len(candidate_by_id) != len(candidate_rows):
        raise ValueError("candidate registries contain duplicate tool IDs")

    return {
        "paths": paths,
        "catalog": catalog,
        "base_pools": base_pools,
        "neighbor_matrix": neighbor_matrix,
        "relations": relations,
        "contracts": contracts,
        "audit_config": audit_config,
        "candidate_by_id": candidate_by_id,
    }


def neighbor_assignment(config: dict[str, Any], sources: dict[str, Any]) -> dict[str, Any]:
    target_id = config["target_tool_id"]
    target_matrix = next(
        row
        for row in sources["neighbor_matrix"]["targets"]
        if row["target_tool_id"] == target_id
    )
    baseline_lexical = {
        row["candidate_tool_id"] for row in target_matrix["lexical_candidates"]
    }
    relation_rows = sources["relations"]["relations"]
    candidate_lexical = {
        row["candidate_tool_id"]
        for row in relation_rows
        if row["target_tool_id"] == target_id and row["relation_type"] == "lexical"
    }
    contract_mismatch = {
        row["candidate_tool_id"]
        for row in relation_rows
        if row["target_tool_id"] == target_id
        and row["relation_type"] == "contract_mismatch"
    }
    expected_lexical = set(config["lexical_neighbor_ids"])
    expected_contract = set(config["contract_mismatch_neighbor_ids"])
    if baseline_lexical | candidate_lexical != expected_lexical:
        raise ValueError("frozen A003 lexical-neighbor assignment does not match evidence")
    if contract_mismatch != expected_contract:
        raise ValueError("frozen A003 contract-mismatch assignment does not match evidence")
    if expected_lexical & expected_contract:
        raise ValueError("A003 neighbor types must be disjoint")
    if len(expected_lexical) != 8 or len(expected_contract) != 8:
        raise ValueError("A003 requires exactly eight neighbors of each type")

    return {
        "candidate_id": config["candidate_id"],
        "target_tool_id": target_id,
        "lexical_neighbor_ids": config["lexical_neighbor_ids"],
        "lexical_evidence_sources": {
            "formal_catalog_algorithmic": sorted(baseline_lexical),
            "admitted_candidate_registry": sorted(candidate_lexical),
        },
        "functional_overlap_interface_neighbor_ids": config[
            "contract_mismatch_neighbor_ids"
        ],
        "evidence_relation_type": "contract_mismatch",
        "functional_overlap_operationalization": config[
            "functional_overlap_operationalization"
        ],
        "expert_validated_functional_overlap": False,
        "confirmatory_use_allowed": False,
        "interpretation_limit": (
            "The functional_overlap label is retained only for compatibility with the "
            "frozen statistical interface. These neighbors operationalize contract-derived "
            "applicability mismatch, not expert-confirmed metallurgical functional overlap."
        ),
    }


def neutral_universe(
    config: dict[str, Any],
    sources: dict[str, Any],
    assignment: dict[str, Any],
) -> dict[str, Any]:
    target_id = config["target_tool_id"]
    catalog_entries = sources["catalog"]["entries"]
    catalog_by_id = {row["tool_id"]: row for row in catalog_entries}
    target = catalog_by_id[target_id]
    contract_by_id = {
        row["tool_id"]: structured_contract(row)
        for row in sources["contracts"]["contracts"]
    }
    target_contract = contract_by_id[target_id]
    assigned = set(config["lexical_neighbor_ids"]) | set(
        config["contract_mismatch_neighbor_ids"]
    )

    relation_candidate_ids = {
        row["candidate_tool_id"] for row in sources["relations"]["relations"]
    }
    non_target_candidates = []
    excluded_screening = []
    for candidate_id in sorted(relation_candidate_ids - assigned):
        candidate = sources["candidate_by_id"][candidate_id]
        score = score_pair(
            target,
            candidate,
            target_contract,
            structured_contract(candidate),
            sources["audit_config"],
        )
        if score["algorithmic_lexical_candidate"] or score[
            "provable_contract_mismatch_neighbor"
        ]:
            excluded_screening.append(
                {
                    "candidate_tool_id": candidate_id,
                    "algorithmic_lexical_candidate": score[
                        "algorithmic_lexical_candidate"
                    ],
                    "provable_contract_mismatch_neighbor": score[
                        "provable_contract_mismatch_neighbor"
                    ],
                    "name_bigram_dice": score["name_bigram_dice"],
                    "contract_text_bigram_dice": score[
                        "contract_text_bigram_dice"
                    ],
                    "input_bigram_dice": score["input_bigram_dice"],
                    "output_bigram_dice": score["output_bigram_dice"],
                }
            )
        else:
            non_target_candidates.append(candidate_id)

    if non_target_candidates != config["expected_safe_neutral_candidate_ids"]:
        raise ValueError("safe neutral candidate set changed")
    if [row["candidate_tool_id"] for row in excluded_screening] != config[
        "expected_additional_a003_screening_exclusions"
    ]:
        raise ValueError("additional A003 screening exclusion set changed")

    formal_neutral_ids = [
        row["tool_id"] for row in catalog_entries if row["tool_id"] not in assigned
    ]
    if target_id not in formal_neutral_ids:
        raise ValueError("target must remain in the neutral universe")
    all_ids = formal_neutral_ids + non_target_candidates
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("neutral universe contains duplicate IDs")
    if len(all_ids) < max(config["pool_sizes"]):
        raise ValueError("neutral universe cannot support the largest zero-dose pool")

    return {
        "neutral_ids": all_ids,
        "formal_neutral_count": len(formal_neutral_ids),
        "safe_candidate_ids": non_target_candidates,
        "additional_screening_exclusions": excluded_screening,
    }


def selected_neighbors(
    config: dict[str, Any],
    neighbor_type: str,
    count: int,
    repeat: str,
) -> list[str]:
    if count == 0:
        return []
    source = (
        config["lexical_neighbor_ids"]
        if neighbor_type == "lexical"
        else config["contract_mismatch_neighbor_ids"]
    )
    if count == 8:
        return list(source)
    if count != 4:
        raise ValueError(f"unsupported neighbor dose: {count}")
    return [source[index] for index in config["four_neighbor_index_selection"][repeat]]


def order_pool(
    config: dict[str, Any],
    repeat: str,
    size: int,
    neutral_ids: list[str],
    neighbor_ids: list[str],
) -> tuple[list[str], list[int]]:
    target_id = config["target_tool_id"]
    target_position = config["target_position_1_based"][str(size)][repeat]
    if not 1 <= target_position <= size:
        raise ValueError("registered target position is outside the pool")
    available_positions = [
        position for position in range(1, size + 1) if position != target_position
    ]
    slot_order = ranked(
        available_positions,
        config["registered_order_seed"],
        "neighbor-slots",
        repeat,
        size,
    )
    neighbor_positions = sorted(slot_order[: len(neighbor_ids)])
    neighbor_order = ranked(
        neighbor_ids,
        config["registered_order_seed"],
        "neighbor-order",
        repeat,
        size,
    )
    neutral_distractors = [tool_id for tool_id in neutral_ids if tool_id != target_id]
    result: list[str | None] = [None] * size
    result[target_position - 1] = target_id
    for position, tool_id in zip(neighbor_positions, neighbor_order):
        result[position - 1] = tool_id
    neutral_iterator = iter(neutral_distractors)
    for index, tool_id in enumerate(result):
        if tool_id is None:
            result[index] = next(neutral_iterator)
    ordered = [str(tool_id) for tool_id in result]
    if len(ordered) != len(set(ordered)):
        raise ValueError("constructed pool contains duplicate tool IDs")
    return ordered, neighbor_positions


def build(config: dict[str, Any]) -> dict[str, Any]:
    observed_conditions = [
        (
            row["near_neighbor_type"],
            row["near_neighbor_count"],
            row["evidence_relation_type"],
        )
        for row in config["conditions"]
    ]
    if config["pool_sizes"] != EXPECTED_POOL_SIZES:
        raise ValueError("pool_sizes must remain the frozen 17/50/100/120 design")
    if config["pool_repeats"] != EXPECTED_POOL_REPEATS:
        raise ValueError("pool_repeats must remain the frozen A-E design")
    if observed_conditions != EXPECTED_CONDITIONS:
        raise ValueError("conditions must remain the frozen five-condition design")
    if config["formal_catalog_mutation_allowed"]:
        raise ValueError("formal_catalog_mutation_allowed must remain false")
    if config["formal_pool_generation_allowed"]:
        raise ValueError("formal_pool_generation_allowed must remain false")
    if config["external_api_calls_authorized"]:
        raise ValueError("external_api_calls_authorized must remain false")
    if config["expert_validated_functional_overlap"]:
        raise ValueError("expert_validated_functional_overlap must remain false")
    if config["confirmatory_use_allowed"]:
        raise ValueError("confirmatory_use_allowed must remain false")

    sources = load_sources(config)
    if len(sources["catalog"]["entries"]) != 120:
        raise ValueError("bound formal catalog must remain exactly 120 entries")
    base_sizes = [row["tool_count"] for row in sources["base_pools"]["pools"]]
    if base_sizes != config["pool_sizes"]:
        raise ValueError("base pool sizes no longer match the controlled design")

    assignment = neighbor_assignment(config, sources)
    neutral = neutral_universe(config, sources, assignment)
    target_id = config["target_tool_id"]
    records = []
    for repeat in config["pool_repeats"]:
        repeat_distractors = ranked(
            [tool_id for tool_id in neutral["neutral_ids"] if tool_id != target_id],
            config["registered_order_seed"],
            "neutral-order",
            repeat,
        )
        for size in config["pool_sizes"]:
            for condition in config["conditions"]:
                count = condition["near_neighbor_count"]
                chosen_neighbors = selected_neighbors(
                    config,
                    condition["near_neighbor_type"],
                    count,
                    repeat,
                )
                selected_neutral = [target_id] + repeat_distractors[: size - count - 1]
                tool_order, neighbor_positions = order_pool(
                    config,
                    repeat,
                    size,
                    selected_neutral,
                    chosen_neighbors,
                )
                records.append(
                    {
                        "pool_id": (
                            f"E3-A003-{repeat}-{size}-"
                            f"{condition_key(condition).upper()}-CANDIDATE-V1"
                        ),
                        "target_tool_id": target_id,
                        "tool_pool_size": size,
                        "pool_design": config["pool_design"],
                        "pool_repeat": repeat,
                        "near_neighbor_type": condition["near_neighbor_type"],
                        "near_neighbor_count": count,
                        "evidence_relation_type": condition["evidence_relation_type"],
                        "functional_overlap_operationalization": (
                            config["functional_overlap_operationalization"]
                            if condition["near_neighbor_type"] == "functional_overlap"
                            else None
                        ),
                        "expert_validated_functional_overlap": False,
                        "confirmatory_use_allowed": False,
                        "neutral_tool_ids": [
                            tool_id for tool_id in tool_order if tool_id not in chosen_neighbors
                        ],
                        "near_neighbor_tool_ids": chosen_neighbors,
                        "neighbor_slot_positions_1_based": neighbor_positions,
                        "target_position_1_based": tool_order.index(target_id) + 1,
                        "tool_order_seed": config["registered_order_seed"],
                        "tool_order": tool_order,
                        "schema_token_count": None,
                        "schema_token_count_status": "pending_frozen_tokenizer_measurement",
                    }
                )

    formal_by_id = {row["tool_id"]: row for row in sources["catalog"]["entries"]}
    used_ids = {tool_id for row in records for tool_id in row["tool_order"]}
    schema_entries = []
    for tool_id in sorted(used_ids):
        if tool_id in formal_by_id:
            entry = deepcopy(formal_by_id[tool_id])
            entry["schema_origin"] = "bound_120_catalog"
        else:
            entry = deepcopy(sources["candidate_by_id"][tool_id])
            entry["schema_origin"] = "admitted_nonformal_candidate_registry"
        schema_entries.append(entry)

    audit = audit_pools(config, records, assignment, neutral, used_ids, schema_entries)
    report = {
        "candidate_id": config["candidate_id"],
        "status": "candidate_generated_nonformal",
        "target_tool_id": target_id,
        "pool_record_count": len(records),
        "pool_sizes": config["pool_sizes"],
        "pool_repeats": config["pool_repeats"],
        "condition_count": len(config["conditions"]),
        "lexical_neighbor_count": len(config["lexical_neighbor_ids"]),
        "contract_mismatch_proxy_neighbor_count": len(
            config["contract_mismatch_neighbor_ids"]
        ),
        "neutral_universe_count": len(neutral["neutral_ids"]),
        "schema_registry_entry_count": len(schema_entries),
        "all_pool_invariants_passed": audit["all_pool_invariants_passed"],
        "formal_catalog_size": len(formal_by_id),
        "formal_catalog_mutated": False,
        "formal_pool_generation_allowed": False,
        "functional_overlap_operationalization": config[
            "functional_overlap_operationalization"
        ],
        "expert_validated_functional_overlap": False,
        "confirmatory_use_allowed": False,
        "schema_token_measurement_status": "pending_frozen_tokenizer_measurement",
        "external_api_calls": 0,
        "external_api_calls_authorized": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "next_gate": (
            "independent review of the proxy interpretation and pool audit before any "
            "development routing run"
        ),
    }
    return {
        "assignment": assignment,
        "manifest": {
            "schema_version": "1.0",
            "candidate_id": config["candidate_id"],
            "pool_record_count": len(records),
            "records": records,
        },
        "schema_registry": {
            "schema_version": "1.0",
            "candidate_id": config["candidate_id"],
            "entry_count": len(schema_entries),
            "entries": schema_entries,
        },
        "audit": audit,
        "report": report,
    }


def audit_pools(
    config: dict[str, Any],
    records: list[dict[str, Any]],
    assignment: dict[str, Any],
    neutral: dict[str, Any],
    used_ids: set[str],
    schema_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_count = (
        len(config["pool_repeats"])
        * len(config["pool_sizes"])
        * len(config["conditions"])
    )
    checks: dict[str, bool] = {}
    checks["record_count"] = len(records) == expected_count
    checks["pool_ids_unique"] = len({row["pool_id"] for row in records}) == len(records)
    checks["exact_size_and_unique_tools"] = all(
        len(row["tool_order"]) == row["tool_pool_size"]
        and len(set(row["tool_order"])) == row["tool_pool_size"]
        for row in records
    )
    checks["target_present_once"] = all(
        row["tool_order"].count(config["target_tool_id"]) == 1 for row in records
    )
    checks["registered_target_positions"] = all(
        row["target_position_1_based"]
        == config["target_position_1_based"][str(row["tool_pool_size"])][
            row["pool_repeat"]
        ]
        for row in records
    )
    checks["exact_neighbor_dose"] = all(
        len(row["near_neighbor_tool_ids"]) == row["near_neighbor_count"]
        and set(row["near_neighbor_tool_ids"]).issubset(row["tool_order"])
        for row in records
    )
    all_neighbors = set(config["lexical_neighbor_ids"]) | set(
        config["contract_mismatch_neighbor_ids"]
    )
    checks["no_neighbor_leakage"] = all(
        set(row["tool_order"]) & all_neighbors == set(row["near_neighbor_tool_ids"])
        for row in records
    )
    checks["same_irrelevant_base_by_dose"] = True
    checks["same_neighbor_slots_by_dose"] = True
    for repeat in config["pool_repeats"]:
        for size in config["pool_sizes"]:
            for count in (4, 8):
                pair = [
                    row
                    for row in records
                    if row["pool_repeat"] == repeat
                    and row["tool_pool_size"] == size
                    and row["near_neighbor_count"] == count
                ]
                checks["same_irrelevant_base_by_dose"] &= (
                    len(pair) == 2
                    and pair[0]["neutral_tool_ids"] == pair[1]["neutral_tool_ids"]
                )
                checks["same_neighbor_slots_by_dose"] &= (
                    len(pair) == 2
                    and pair[0]["neighbor_slot_positions_1_based"]
                    == pair[1]["neighbor_slot_positions_1_based"]
                )
    checks["nested_sets_by_repeat_and_condition"] = True
    for repeat in config["pool_repeats"]:
        for condition in config["conditions"]:
            rows = sorted(
                (
                    row
                    for row in records
                    if row["pool_repeat"] == repeat
                    and row["near_neighbor_type"] == condition["near_neighbor_type"]
                    and row["near_neighbor_count"] == condition["near_neighbor_count"]
                ),
                key=lambda row: row["tool_pool_size"],
            )
            checks["nested_sets_by_repeat_and_condition"] &= all(
                set(left["tool_order"]).issubset(right["tool_order"])
                for left, right in zip(rows, rows[1:])
            )
    checks["four_dose_balanced"] = True
    four_balance: dict[str, dict[str, int]] = {}
    for neighbor_type, ids in (
        ("lexical", config["lexical_neighbor_ids"]),
        ("functional_overlap", config["contract_mismatch_neighbor_ids"]),
    ):
        counts = Counter()
        for repeat in config["pool_repeats"]:
            counts.update(selected_neighbors(config, neighbor_type, 4, repeat))
        frequencies = {tool_id: counts[tool_id] for tool_id in ids}
        four_balance[neighbor_type] = frequencies
        checks["four_dose_balanced"] &= max(frequencies.values()) - min(
            frequencies.values()
        ) <= 1
    checks["schema_registry_complete"] = {
        row["tool_id"] for row in schema_entries
    } == used_ids
    checks["neutral_capacity"] = len(neutral["neutral_ids"]) >= max(
        config["pool_sizes"]
    )
    checks["proxy_not_expert_gold"] = (
        assignment["functional_overlap_operationalization"]
        == "contract_mismatch_proxy"
        and not assignment["expert_validated_functional_overlap"]
        and not assignment["confirmatory_use_allowed"]
    )
    checks["no_formal_or_external_mutation"] = (
        not config["formal_catalog_mutation_allowed"]
        and not config["formal_pool_generation_allowed"]
        and not config["external_api_calls_authorized"]
    )
    return {
        "candidate_id": config["candidate_id"],
        "checks": checks,
        "all_pool_invariants_passed": all(checks.values()),
        "four_dose_selection_frequency": four_balance,
        "neutral_universe": {
            "count": len(neutral["neutral_ids"]),
            "formal_neutral_count": neutral["formal_neutral_count"],
            "safe_candidate_ids": neutral["safe_candidate_ids"],
            "additional_a003_screening_exclusions": neutral[
                "additional_screening_exclusions"
            ],
        },
        "interpretation": {
            "statistical_interface_label": "functional_overlap",
            "actual_evidence_relation": "contract_mismatch",
            "expert_validated": False,
            "formal_h3_claim_allowed": False,
        },
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    result = build(config)
    if not result["audit"]["all_pool_invariants_passed"]:
        failed = [
            name for name, passed in result["audit"]["checks"].items() if not passed
        ]
        raise ValueError(f"pool audit failed: {failed}")
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "a003_neighbor_assignment.json": result["assignment"],
        "a003_controlled_pool_manifest.json": result["manifest"],
        "a003_pool_schema_registry.json": result["schema_registry"],
        "a003_pool_audit.json": result["audit"],
        "a003_pool_construction_report.json": result["report"],
        "a003_controlled_pool_config_snapshot.json": config,
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    manifest = {
        "candidate_id": config["candidate_id"],
        "artifact_count": len(artifacts),
        "artifacts": [
            {
                "filename": filename,
                "sha256": sha256_file(output_dir / filename),
                "bytes": (output_dir / filename).stat().st_size,
            }
            for filename in sorted(artifacts)
        ],
    }
    write_json(output_dir / "artifact_manifest.json", manifest)
    return result["report"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    report = build_outputs(Path(args.output_dir).resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
