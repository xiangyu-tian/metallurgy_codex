"""Complete the nonformal A004 dose-0/4 pool grid without API calls."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing import build_e3_a004_hardcase_opening as old


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("a004_dose4_complete_pool_config_v1.json")
EXPECTED_SIZES = [17, 50, 100, 120]
EXPECTED_REPEATS = ["A", "B", "C", "D", "E"]
EXPECTED_CONDITIONS = ["none_0", "lexical_4", "functional_overlap_4"]


def ranked(values: list[str], seed: str, *parts: object) -> list[str]:
    prefix = "|".join([seed, *(str(part) for part in parts)])
    return sorted(
        values,
        key=lambda value: (
            hashlib.sha256(f"{prefix}|{value}".encode("utf-8")).hexdigest(),
            value,
        ),
    )


def validate_config(config: dict[str, Any]) -> None:
    if config["target_tool_id"] != "A004":
        raise ValueError("target tool must remain A004")
    if config["pool_sizes"] != EXPECTED_SIZES or config["pool_repeats"] != EXPECTED_REPEATS:
        raise ValueError("A004 pool size/repeat grid changed")
    conditions = config["neighbor_conditions"]
    if [row["condition_id"] for row in conditions] != EXPECTED_CONDITIONS:
        raise ValueError("A004 condition grid changed")
    if [(row["near_neighbor_type"], row["near_neighbor_count"]) for row in conditions] != [
        ("none", 0), ("lexical", 4), ("functional_overlap", 4)
    ]:
        raise ValueError("A004 dose grid changed")
    if conditions[2]["evidence_relation_type"] != "contract_mismatch":
        raise ValueError("functional interface must retain contract-mismatch evidence label")
    for field in (
        "external_api_calls_authorized", "tool_execution_allowed",
        "new_tool_identity_creation_allowed", "independent_validation_split_access_allowed",
        "confirmatory_inference_allowed", "formal_pool_generation_allowed", "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")
    if config["cf05_status"] != "in_progress":
        raise ValueError("pool completion cannot pass CF-05")


def load_sources(config: dict[str, Any]) -> dict[str, Any]:
    paths = {name: old.validate_binding(binding) for name, binding in config["bindings"].items()}
    return {name: old.load_json(path) for name, path in paths.items()}


def relation_snapshot(config: dict[str, Any], sources: dict[str, Any]) -> dict[str, Any]:
    legacy_config = {
        "opening_id": config["candidate_id"],
        "neighbor_conditions": [
            {
                **deepcopy(row),
                "near_neighbor_type": row["evidence_relation_type"],
            }
            for row in config["neighbor_conditions"]
        ],
    }
    snapshot = old.validate_relation_evidence(legacy_config, sources)
    snapshot["candidate_id"] = config["candidate_id"]
    snapshot["functional_overlap_operationalization"] = "contract_mismatch"
    snapshot["expert_validated_functional_overlap"] = False
    snapshot["confirmatory_use_allowed"] = False
    return snapshot


def anchor_lookup(sources: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    aliases = {
        "none_0": "none_0",
        "lexical_4": "lexical_4",
        "contract_mismatch_4": "functional_overlap_4",
    }
    rows = sources["existing_a004_pools"]["pools"]
    if len(rows) != 6:
        raise ValueError("existing A004 anchor pool count changed")
    result = {(aliases[row["condition_id"]], int(row["tool_pool_size"])): row for row in rows}
    if set(result) != {(condition, size) for condition in EXPECTED_CONDITIONS for size in (17, 120)}:
        raise ValueError("existing A004 anchor pool grid changed")
    return result


def anchored_intermediate(anchor17: list[str], anchor120: list[str], size: int) -> list[str]:
    if not set(anchor17).issubset(anchor120):
        raise ValueError("legacy 17-tool anchor is not nested in legacy 120-tool anchor")
    selected = set(anchor17)
    for tool_id in anchor120:
        if len(selected) >= size:
            break
        selected.add(tool_id)
    if len(selected) != size:
        raise ValueError(f"cannot interpolate anchored pool size {size}")
    return [tool_id for tool_id in anchor120 if tool_id in selected]


def build_pools(
    config: dict[str, Any],
    sources: dict[str, Any],
    entry_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    conditions = {row["condition_id"]: row for row in config["neighbor_conditions"]}
    all_neighbors = {tool_id for row in conditions.values() for tool_id in row["tool_ids"]}
    neutral_ids = sorted(set(entry_by_id) - all_neighbors - {"A004"})
    if len(neutral_ids) < 119:
        raise ValueError("entry registry cannot support a 120-tool zero-dose pool")
    anchors = anchor_lookup(sources)
    rows: list[dict[str, Any]] = []
    for repeat in EXPECTED_REPEATS:
        repeat_neutral = ranked(neutral_ids, config["deterministic_seed"], repeat, "neutral")
        for condition_id in EXPECTED_CONDITIONS:
            condition = conditions[condition_id]
            neighbors = condition["tool_ids"]
            for size in EXPECTED_SIZES:
                if repeat == "A":
                    if size in (17, 120):
                        tool_order = deepcopy(anchors[(condition_id, size)]["tool_order"])
                    else:
                        tool_order = anchored_intermediate(
                            anchors[(condition_id, 17)]["tool_order"],
                            anchors[(condition_id, 120)]["tool_order"],
                            size,
                        )
                else:
                    neutral_count = size - 1 - len(neighbors)
                    selected = ["A004", *repeat_neutral[:neutral_count], *neighbors]
                    tool_order = ranked(selected, config["deterministic_seed"], repeat, condition_id, "order")
                if len(tool_order) != size or len(set(tool_order)) != size:
                    raise ValueError(f"invalid pool cardinality for {repeat}/{condition_id}/{size}")
                if "A004" not in tool_order or any(tool_id not in entry_by_id for tool_id in tool_order):
                    raise ValueError(f"invalid schema membership for {repeat}/{condition_id}/{size}")
                rows.append(
                    {
                        "pool_id": f"A004-{condition_id.upper()}-{size}-R{repeat}",
                        "target_tool_id": "A004",
                        "pool_design": "controlled_dose_development",
                        "pool_repeat": repeat,
                        "condition_id": condition_id,
                        "near_neighbor_type": condition["near_neighbor_type"],
                        "evidence_relation_type": condition["evidence_relation_type"],
                        "near_neighbor_count": condition["near_neighbor_count"],
                        "selected_neighbor_tool_ids": deepcopy(neighbors),
                        "tool_pool_size": size,
                        "tool_order": tool_order,
                        "tool_order_sha256": old.json_hash(tool_order),
                        "full_schema_view_sha256": old.json_hash([entry_by_id[x]["openai_tool"] for x in tool_order]),
                        "legacy_anchor_preserved": repeat == "A" and size in (17, 120),
                        "formal_pool_use_allowed": False,
                        "confirmatory_use_allowed": False,
                    }
                )

    by_key = {(row["pool_repeat"], row["condition_id"], row["tool_pool_size"]): row for row in rows}
    if len(rows) != 60 or len(by_key) != 60:
        raise ValueError("A004 dose-4 grid must contain 60 unique pools")
    checks: list[dict[str, Any]] = []
    for repeat in EXPECTED_REPEATS:
        for condition_id in EXPECTED_CONDITIONS:
            condition = conditions[condition_id]
            own = set(condition["tool_ids"])
            other = all_neighbors - own
            previous: set[str] = set()
            for size in EXPECTED_SIZES:
                pool = by_key[(repeat, condition_id, size)]
                ids = set(pool["tool_order"])
                passed = (
                    len(ids) == size
                    and list(pool["tool_order"]).count("A004") == 1
                    and own.issubset(ids)
                    and not (ids & other)
                    and previous.issubset(ids)
                )
                checks.append({
                    "pool_id": pool["pool_id"],
                    "exact_size_target_dose_no_leakage_and_nested": passed,
                })
                if not passed:
                    raise ValueError(f"pool invariant failed: {pool['pool_id']}")
                previous = ids
        for size in EXPECTED_SIZES:
            lexical = set(by_key[(repeat, "lexical_4", size)]["tool_order"]) - {"A004"} - set(conditions["lexical_4"]["tool_ids"])
            functional = set(by_key[(repeat, "functional_overlap_4", size)]["tool_order"]) - {"A004"} - set(conditions["functional_overlap_4"]["tool_ids"])
            if lexical != functional:
                raise ValueError(f"paired dose-4 neutral bases differ for {repeat}/{size}")

    compatibility_rows = []
    for condition_id in EXPECTED_CONDITIONS:
        for size in (17, 120):
            legacy = anchors[(condition_id, size)]
            current = by_key[("A", condition_id, size)]
            exact = legacy["tool_order"] == current["tool_order"]
            compatibility_rows.append({
                "condition_id": condition_id,
                "tool_pool_size": size,
                "legacy_pool_id": legacy["pool_id"],
                "current_pool_id": current["pool_id"],
                "tool_order_exact_match": exact,
                "tool_order_sha256_exact_match": legacy["tool_order_sha256"] == current["tool_order_sha256"],
            })
    if not all(row["tool_order_exact_match"] and row["tool_order_sha256_exact_match"] for row in compatibility_rows):
        raise ValueError("legacy A004 anchor compatibility failed")

    manifest = {
        "schema_version": "1.0",
        "candidate_id": config["candidate_id"],
        "target_tool_id": "A004",
        "pool_count": len(rows),
        "pool_sizes": EXPECTED_SIZES,
        "pool_repeats": EXPECTED_REPEATS,
        "condition_count": 3,
        "records": rows,
        "external_api_calls": 0,
        "formal_pool_use_allowed": False,
        "confirmatory_use_allowed": False,
    }
    audit = {
        "schema_version": "1.0",
        "candidate_id": config["candidate_id"],
        "all_pool_invariants_passed": all(row["exact_size_target_dose_no_leakage_and_nested"] for row in checks),
        "pool_count": len(rows),
        "legacy_anchor_check_count": len(compatibility_rows),
        "legacy_anchor_checks_passed": all(row["tool_order_exact_match"] for row in compatibility_rows),
        "paired_dose4_neutral_bases_equal": True,
        "nested_size_chains_checked": 15,
        "checks": checks,
        "external_api_calls": 0,
        "new_tool_identities_created": 0,
        "independent_validation_split_accessed": False,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
    }
    compatibility = {
        "schema_version": "1.0",
        "candidate_id": config["candidate_id"],
        "policy": config["anchor_policy"],
        "all_six_legacy_anchors_preserved": True,
        "rows": compatibility_rows,
    }
    return manifest, {"audit": audit, "compatibility": compatibility}


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    sources = load_sources(config)
    if sources["method_freeze_adoption"]["decision"] != "adopted":
        raise ValueError("CF-05 development method freeze is not adopted")
    entries, entry_by_id = old.load_entry_registry(sources)
    relations = relation_snapshot(config, sources)
    manifest, evidence = build_pools(config, sources, entry_by_id)
    used_ids = sorted({tool_id for row in manifest["records"] for tool_id in row["tool_order"]})
    schema_registry = {
        "schema_version": "1.0",
        "candidate_id": config["candidate_id"],
        "entry_count": len(used_ids),
        "entries": [entry_by_id[tool_id] for tool_id in used_ids],
        "formal_catalog_mutated": False,
    }
    report = {
        "schema_version": "1.0",
        "candidate_id": config["candidate_id"],
        "status": "a004_dose4_development_pool_grid_complete",
        "pool_count": manifest["pool_count"],
        "strict_a004_0_4_8_required_pool_count": 100,
        "remaining_a004_dose8_pool_count": 40,
        "relation_evidence_count": relations["relation_count"],
        "legacy_anchor_count": evidence["audit"]["legacy_anchor_check_count"],
        "legacy_anchors_preserved": evidence["compatibility"]["all_six_legacy_anchors_preserved"],
        "methods_changed": False,
        "external_api_calls": 0,
        "tool_calls_executed": 0,
        "new_tool_identities_created": 0,
        "independent_validation_split_accessed": False,
        "confirmatory_inference_allowed": False,
        "formal_pool_generation_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "next_gate": "source and validate four additional lexical and four additional functional-neighbor relations before constructing A004 dose-8 pools",
    }
    return {
        "relations": relations,
        "manifest": manifest,
        "schema_registry": schema_registry,
        "audit": evidence["audit"],
        "compatibility": evidence["compatibility"],
        "report": report,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = old.load_json(CONFIG_PATH)
    built = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a004_dose4_config_snapshot.json": config,
        "a004_dose4_relation_evidence_snapshot.json": built["relations"],
        "a004_dose4_controlled_pool_manifest.json": built["manifest"],
        "a004_dose4_pool_schema_registry.json": built["schema_registry"],
        "a004_dose4_pool_audit.json": built["audit"],
        "a004_dose4_legacy_compatibility_report.json": built["compatibility"],
        "a004_dose4_construction_report.json": built["report"],
    }
    for filename, value in artifacts.items():
        old.write_json(output_dir / filename, value)
    paths = sorted(output_dir.iterdir(), key=lambda path: path.name)
    old.write_json(
        output_dir / "artifact_manifest.json",
        {
            "schema_version": "1.0",
            "candidate_id": config["candidate_id"],
            "artifact_count": len(paths),
            "artifacts": [
                {"filename": path.name, "sha256": old.sha256_file(path), "bytes": path.stat().st_size}
                for path in paths
            ],
        },
    )
    return built["report"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else WORKSPACE / args.output_dir
    print(json.dumps(build_outputs(output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
