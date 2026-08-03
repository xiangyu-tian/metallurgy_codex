"""Audit whether the 120-entry catalog can support E3 0/4/8 pools.

This module ranks mechanically reproducible lexical candidates and requires a
structured contract mismatch plus functional similarity for contract-neighbor
eligibility.  It never fills missing slots with weakly related tools and never
emits a formal controlled-dose pool when the prerequisites are not met.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("neighbor_audit_config_v1_1.json")


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


def validate_bound_file(path: Path, expected_hash: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256_file(path)
    if actual != expected_hash.lower():
        raise ValueError(f"bound file hash mismatch for {path}: {actual}")


def normalize_text(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.lower())


def bigrams(value: str, stop_terms: list[str] | None = None) -> set[str]:
    normalized = normalize_text(value)
    for term in stop_terms or []:
        normalized = normalized.replace(normalize_text(term), "")
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[index:index + 2] for index in range(len(normalized) - 1)}


def dice(left: str, right: str, stop_terms: list[str] | None = None) -> float:
    left_set = bigrams(left, stop_terms)
    right_set = bigrams(right, stop_terms)
    if not left_set or not right_set:
        return 0.0
    return 2.0 * len(left_set & right_set) / (len(left_set) + len(right_set))


def contract_text(entry: dict[str, Any]) -> str:
    return " ".join(
        str(entry[field])
        for field in ("tool_name", "core_method", "main_input", "main_output")
    )


def structured_contract(contract: dict[str, Any] | None) -> dict[str, Any]:
    if contract is None:
        return {}
    return {
        "supported_systems": contract.get("supported_systems"),
        "data_or_model_version": contract.get("data_or_model_version"),
        "service_status": contract.get("service_status"),
    }


def mismatch_dimensions(
    target_contract: dict[str, Any],
    candidate_contract: dict[str, Any],
    dimensions: list[str],
) -> list[str]:
    mismatches = []
    for dimension in dimensions:
        left = target_contract.get(dimension)
        right = candidate_contract.get(dimension)
        if left is not None and right is not None and left != right:
            mismatches.append(dimension)
    return mismatches


def score_pair(
    target: dict[str, Any],
    candidate: dict[str, Any],
    target_contract: dict[str, Any],
    candidate_contract: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    stop_terms = config.get("lexical_stop_terms", [])
    name_score = dice(target["tool_name"], candidate["tool_name"], stop_terms)
    text_score = dice(contract_text(target), contract_text(candidate), stop_terms)
    input_score = dice(target["main_input"], candidate["main_input"], stop_terms)
    output_score = dice(target["main_output"], candidate["main_output"], stop_terms)
    input_output_overlap = (
        input_score >= config["functional_similarity_dice_min"]
        and output_score >= config["functional_similarity_dice_min"]
    )
    same_core_method = target["core_method"] == candidate["core_method"]
    mismatches = mismatch_dimensions(
        target_contract,
        candidate_contract,
        config["contract_mismatch_dimensions"],
    )
    lexical_candidate = (
        not same_core_method
        and (
            name_score >= config["lexical_name_dice_min"]
            or text_score >= config["lexical_contract_text_dice_min"]
        )
    )
    contract_neighbor = (
        (same_core_method or input_output_overlap)
        and bool(mismatches)
    )
    return {
        "target_tool_id": target["tool_id"],
        "candidate_tool_id": candidate["tool_id"],
        "candidate_tool_name": candidate["tool_name"],
        "candidate_lifecycle_status": candidate["lifecycle_status"],
        "same_scenario": target["scenario"] == candidate["scenario"],
        "same_core_method": same_core_method,
        "name_bigram_dice": round(name_score, 6),
        "contract_text_bigram_dice": round(text_score, 6),
        "input_bigram_dice": round(input_score, 6),
        "output_bigram_dice": round(output_score, 6),
        "structured_contract_available": bool(candidate_contract),
        "structured_mismatch_dimensions": mismatches,
        "algorithmic_lexical_candidate": lexical_candidate,
        "provable_contract_mismatch_neighbor": contract_neighbor,
    }


def capacity_requirements(pool_size: int, max_dose: int) -> dict[str, int]:
    return {
        "single_neighbor_type_min_catalog_size": pool_size + max_dose,
        "two_disjoint_neighbor_types_min_catalog_size": pool_size + 2 * max_dose,
    }


def audit(config: dict[str, Any]) -> dict[str, Any]:
    catalog_path = WORKSPACE / config["catalog_path"]
    pool_manifest_path = WORKSPACE / config["pool_manifest_path"]
    contracts_path = WORKSPACE / config["verified_contracts_path"]
    validate_bound_file(catalog_path, config["catalog_sha256"])
    validate_bound_file(pool_manifest_path, config["pool_manifest_sha256"])
    validate_bound_file(contracts_path, config["verified_contracts_sha256"])

    catalog_document = load_json(catalog_path)
    entries = catalog_document["entries"]
    entry_by_id = {entry["tool_id"]: entry for entry in entries}
    contracts = load_json(contracts_path)["contracts"]
    contract_by_id = {
        contract["tool_id"]: structured_contract(contract) for contract in contracts
    }
    if set(config["target_tool_ids"]) != set(contract_by_id):
        raise ValueError("target IDs must exactly match the verified_core contracts")

    target_audits = []
    all_pairs = []
    for target_id in config["target_tool_ids"]:
        target = entry_by_id[target_id]
        pair_rows = [
            score_pair(
                target,
                candidate,
                contract_by_id[target_id],
                contract_by_id.get(candidate["tool_id"], {}),
                config,
            )
            for candidate in entries
            if candidate["tool_id"] != target_id
        ]
        pair_rows.sort(
            key=lambda row: (
                row["provable_contract_mismatch_neighbor"],
                row["algorithmic_lexical_candidate"],
                row["contract_text_bigram_dice"],
                row["name_bigram_dice"],
                row["candidate_tool_id"],
            ),
            reverse=True,
        )
        lexical = [row for row in pair_rows if row["algorithmic_lexical_candidate"]]
        contract_neighbors = [
            row for row in pair_rows if row["provable_contract_mismatch_neighbor"]
        ]
        target_audits.append(
            {
                "target_tool_id": target_id,
                "target_tool_name": target["tool_name"],
                "algorithmic_lexical_candidate_count": len(lexical),
                "provable_contract_mismatch_neighbor_count": len(contract_neighbors),
                "has_lexical_8": len(lexical) >= 8,
                "has_contract_mismatch_8": len(contract_neighbors) >= 8,
                "eligible_for_h3_paired_8": (
                    len(lexical) >= 8 and len(contract_neighbors) >= 8
                ),
                "lexical_candidates": lexical,
                "contract_mismatch_neighbors": contract_neighbors,
                "top_screening_rows": pair_rows[:12],
            }
        )
        all_pairs.extend(pair_rows)

    max_dose = max(config["near_neighbor_counts"])
    catalog_size = len(entries)
    capacity = []
    for pool_size in config["pool_sizes"]:
        requirements = capacity_requirements(pool_size, max_dose)
        capacity.append(
            {
                "tool_pool_size": pool_size,
                **requirements,
                "catalog_size": catalog_size,
                "single_type_capacity_feasible": (
                    catalog_size >= requirements["single_neighbor_type_min_catalog_size"]
                ),
                "two_disjoint_type_capacity_feasible": (
                    catalog_size >= requirements[
                        "two_disjoint_neighbor_types_min_catalog_size"
                    ]
                ),
            }
        )

    eligible_targets = [
        row["target_tool_id"]
        for row in target_audits
        if row["eligible_for_h3_paired_8"]
    ]
    return {
        "candidate_matrix": {
            "audit_id": config["audit_id"],
            "method": {
                "lexical": (
                    "character-bigram Dice on frozen catalog fields after removing "
                    "preregistered generic function terms"
                ),
                "lexical_stop_terms": config.get("lexical_stop_terms", []),
                "contract_mismatch": (
                    "functional overlap plus a mismatch in a structured, present-on-both-sides "
                    "contract dimension"
                ),
                "weak_related_fill_forbidden": config["weak_related_fill_forbidden"],
            },
            "targets": target_audits,
            "pair_row_count": len(all_pairs),
        },
        "feasibility": {
            "audit_id": config["audit_id"],
            "catalog_size": catalog_size,
            "near_neighbor_counts": config["near_neighbor_counts"],
            "capacity": capacity,
            "h3_paired_8_eligible_target_ids": eligible_targets,
            "h3_paired_8_eligible_target_count": len(eligible_targets),
            "formal_controlled_dose_pools_generated": False,
            "reason": (
                "structured contract-mismatch neighbors are insufficient and the 120-entry "
                "universe cannot support paired 0/4/8 replacement pools at size 120"
            ),
        },
        "report": {
            "audit_id": config["audit_id"],
            "status": "blocked_evidence_generated",
            "target_count": len(target_audits),
            "catalog_size": catalog_size,
            "h3_paired_8_eligible_target_count": len(eligible_targets),
            "minimum_catalog_size_for_120_single_type": 120 + max_dose,
            "minimum_catalog_size_for_120_two_disjoint_types": 120 + 2 * max_dose,
            "additional_schema_entries_needed_single_type": max(0, 120 + max_dose - catalog_size),
            "additional_schema_entries_needed_two_disjoint_types": max(
                0, 120 + 2 * max_dose - catalog_size
            ),
            "formal_controlled_dose_pools_generated": False,
            "mixed_realistic_120_remains_available": True,
            "external_api_calls": 0,
            "external_api_calls_authorized": False,
            "next_decision": (
                "expand the routing universe before H3 120-tool controlled-dose construction, "
                "or preregister a smaller controlled-dose primary scale"
            ),
        },
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    result = audit(config)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "neighbor_candidate_matrix.json": result["candidate_matrix"],
        "controlled_dose_feasibility.json": result["feasibility"],
        "audit_report.json": result["report"],
        "neighbor_audit_config_snapshot.json": config,
    }
    for filename, value in paths.items():
        write_json(output_dir / filename, value)
    manifest = {
        "audit_id": config["audit_id"],
        "artifact_count": len(paths),
        "artifacts": [
            {
                "filename": filename,
                "sha256": sha256_file(output_dir / filename),
                "bytes": (output_dir / filename).stat().st_size,
            }
            for filename in sorted(paths)
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
