"""Build an unfilled, evidence-bound E3 routing-catalog expansion plan."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("expansion_plan_config_v1.json")


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


def entry_schema() -> dict[str, Any]:
    relation_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "target_tool_id",
            "neighbor_type",
            "scientific_function_distinct",
            "acceptable_tool_equivalent",
            "non_equivalence_evidence_ids",
        ],
        "properties": {
            "target_tool_id": {"type": "string", "enum": ["A001", "A002", "A003", "A004", "B019"]},
            "neighbor_type": {"type": "string", "enum": ["lexical", "contract_mismatch"]},
            "scientific_function_distinct": {"type": "boolean"},
            "acceptable_tool_equivalent": {"type": "boolean"},
            "lexical_name_dice": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
            "lexical_contract_text_dice": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
            "functional_input_dice": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
            "functional_output_dice": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
            "mismatch_dimensions": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["phase", "temperature_range", "pressure_range", "system", "version", "availability"],
                },
                "uniqueItems": True,
            },
            "target_valid_candidate_invalid_fixture_id": {"type": ["string", "null"]},
            "non_equivalence_evidence_ids": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "uniqueItems": True,
            },
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "e3-routing-expansion-entry-v1",
        "title": "E3 routing catalog expansion entry",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "candidate_tool_id",
            "tool_name",
            "semantic_alias",
            "scientific_function",
            "scenario",
            "tool_type",
            "core_method",
            "input_contract",
            "output_contract",
            "applicability_contract",
            "source_provenance",
            "neighbor_relations",
            "independence_evidence_ids",
            "lifecycle_status",
            "review_status",
        ],
        "properties": {
            "candidate_tool_id": {"type": "string", "pattern": "^[A-Z][0-9]{3}$"},
            "tool_name": {"type": "string", "minLength": 2},
            "semantic_alias": {"type": "string", "pattern": "^[a-z][a-z0-9_]{2,63}$"},
            "scientific_function": {"type": "string", "minLength": 4},
            "scenario": {"type": "string", "minLength": 2},
            "tool_type": {"type": "string", "minLength": 2},
            "core_method": {"type": "string", "minLength": 4},
            "input_contract": {
                "type": "object",
                "required": ["parameters", "required", "units"],
                "properties": {
                    "parameters": {"type": "object", "minProperties": 1},
                    "required": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                    "units": {"type": "object"},
                },
            },
            "output_contract": {"type": "object", "minProperties": 1},
            "applicability_contract": {
                "type": "object",
                "additionalProperties": False,
                "required": ["phases", "temperature_range", "pressure_range", "systems", "version", "availability", "known_limitations"],
                "properties": {
                    "phases": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                    "temperature_range": {"type": ["object", "null"]},
                    "pressure_range": {"type": ["object", "null"]},
                    "systems": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                    "version": {"type": "string", "minLength": 1},
                    "availability": {"type": "string", "enum": ["available", "unavailable", "conditional"]},
                    "known_limitations": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                },
            },
            "source_provenance": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["source_id", "title", "locator", "source_type"],
                    "properties": {
                        "source_id": {"type": "string"},
                        "title": {"type": "string"},
                        "locator": {"type": "string"},
                        "source_type": {"type": "string", "enum": ["standard", "primary_documentation", "paper", "software_manual", "model_card"]},
                    },
                },
                "minItems": 1,
            },
            "neighbor_relations": {"type": "array", "items": relation_schema, "minItems": 1},
            "independence_evidence_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "lifecycle_status": {"const": "schema_only_candidate"},
            "review_status": {"type": "string", "enum": ["machine_precheck_pending", "machine_precheck_passed", "rejected"]},
        },
    }


def build_plan(config: dict[str, Any]) -> dict[str, Any]:
    matrix_path = WORKSPACE / config["corrected_audit_matrix_path"]
    feasibility_path = WORKSPACE / config["corrected_feasibility_path"]
    validate_bound_file(matrix_path, config["corrected_audit_matrix_sha256"])
    validate_bound_file(feasibility_path, config["corrected_feasibility_sha256"])
    matrix = load_json(matrix_path)
    feasibility = load_json(feasibility_path)
    target_dose = config["target_neighbor_count_per_type"]

    requirements = []
    slots = []
    for target in matrix["targets"]:
        current_lexical = min(target_dose, target["algorithmic_lexical_candidate_count"])
        current_contract = min(target_dose, target["provable_contract_mismatch_neighbor_count"])
        lexical_gap = target_dose - current_lexical
        contract_gap = target_dose - current_contract
        requirements.append(
            {
                "target_tool_id": target["target_tool_id"],
                "target_tool_name": target["target_tool_name"],
                "current_lexical_count": current_lexical,
                "lexical_gap_to_8": lexical_gap,
                "current_contract_mismatch_count": current_contract,
                "contract_mismatch_gap_to_8": contract_gap,
                "paired_8_ready": lexical_gap == 0 and contract_gap == 0,
            }
        )
        for neighbor_type, gap in (
            ("lexical", lexical_gap),
            ("contract_mismatch", contract_gap),
        ):
            for index in range(1, gap + 1):
                slots.append(
                    {
                        "slot_id": f"{target['target_tool_id']}-{neighbor_type.upper()}-{index:02d}",
                        "target_tool_id": target["target_tool_id"],
                        "neighbor_type": neighbor_type,
                        "slot_status": "unfilled",
                        "candidate_tool_id": None,
                        "relation_evidence_id": None,
                        "may_share_candidate_with_other_target": config[
                            "cross_target_reuse_allowed_only_after_relation_evidence"
                        ],
                        "may_share_candidate_across_types_for_same_target": config[
                            "same_target_cross_type_reuse_allowed"
                        ],
                    }
                )

    lexical_gap_total = sum(row["lexical_gap_to_8"] for row in requirements)
    contract_gap_total = sum(
        row["contract_mismatch_gap_to_8"] for row in requirements
    )
    conservative_distinct_slots = lexical_gap_total + contract_gap_total
    current_size = config["current_catalog_size"]
    capacity_floor = config["minimum_capacity_catalog_size"]
    return {
        "requirement_matrix": {
            "plan_id": config["plan_id"],
            "target_neighbor_count_per_type": target_dose,
            "requirements": requirements,
            "lexical_gap_total": lexical_gap_total,
            "contract_mismatch_gap_total": contract_gap_total,
            "conservative_distinct_slot_count": conservative_distinct_slots,
            "minimum_capacity_catalog_size": capacity_floor,
            "conservative_no_reuse_catalog_size": current_size + conservative_distinct_slots,
            "minimum_unique_expansion_count": capacity_floor - current_size,
            "actual_unique_expansion_count": None,
            "capacity_reserve_after_evidence_based_dedup": None,
            "note": (
                "136 is a capacity floor; target relation gaps remain binding. Cross-target "
                "reuse is counted only after each relation independently passes evidence checks."
            ),
        },
        "slot_template": {
            "plan_id": config["plan_id"],
            "slot_count": len(slots),
            "all_slots_unfilled": True,
            "invented_tool_identity_allowed": config["invented_tool_identity_allowed"],
            "slots": slots,
        },
        "entry_schema": entry_schema(),
        "report": {
            "plan_id": config["plan_id"],
            "status": "requirements_frozen_entries_unfilled",
            "source_audit_id": matrix["audit_id"],
            "source_h3_eligible_target_count": feasibility[
                "h3_paired_8_eligible_target_count"
            ],
            "target_count": len(requirements),
            "lexical_gap_total": lexical_gap_total,
            "contract_mismatch_gap_total": contract_gap_total,
            "conservative_distinct_slot_count": conservative_distinct_slots,
            "minimum_capacity_catalog_size": capacity_floor,
            "conservative_no_reuse_catalog_size": current_size + conservative_distinct_slots,
            "new_tool_entries_created": 0,
            "external_api_calls": 0,
            "external_api_calls_authorized": False,
            "formal_pool_generation_allowed": False,
        },
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    result = build_plan(config)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "expansion_requirement_matrix.json": result["requirement_matrix"],
        "expansion_slot_template.json": result["slot_template"],
        "expansion_entry_schema_v1.json": result["entry_schema"],
        "expansion_plan_report.json": result["report"],
        "expansion_plan_config_snapshot.json": config,
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    manifest = {
        "plan_id": config["plan_id"],
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
