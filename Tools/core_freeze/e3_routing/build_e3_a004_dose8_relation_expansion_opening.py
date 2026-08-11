"""Build the offline source-screening opening for A004 dose-8 relations."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common
from Tools.core_freeze.e3_routing import audit_e3_neighbor_feasibility as scoring


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("a004_dose8_relation_expansion_opening_config_v1.json")


def validate_config(config: dict[str, Any]) -> None:
    if config["target_tool_id"] != "A004":
        raise ValueError("opening target must remain A004")
    if config["starting_relation_counts"] != {"lexical": 4, "functional_overlap": 4}:
        raise ValueError("A004 starting relation counts changed")
    if config["target_relation_counts"] != {"lexical": 8, "functional_overlap": 8}:
        raise ValueError("A004 target relation counts changed")
    if len(config["existing_cross_target_candidates"]) != 1 or len(config["new_source_candidates"]) != 7:
        raise ValueError("opening must screen one reuse candidate and seven new sources")
    for field in (
        "new_tool_identity_creation_authorized", "dependency_installation_authorized",
        "local_candidate_execution_authorized", "external_api_calls_authorized",
        "independent_validation_split_access_allowed", "formal_catalog_mutation_allowed",
        "formal_pool_generation_allowed", "confirmatory_inference_allowed", "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")
    if config["cf05_status"] != "in_progress":
        raise ValueError("source screening cannot pass CF-05")


def load_sources(config: dict[str, Any]) -> dict[str, Any]:
    paths = {name: common.validate_binding(binding) for name, binding in config["bindings"].items()}
    return {name: common.load_json(path) for name, path in paths.items()}


def score_candidate(
    candidate: dict[str, Any],
    target: dict[str, Any],
    target_contract: dict[str, Any],
    audit_config: dict[str, Any],
) -> dict[str, Any]:
    score_row = {
        "tool_id": candidate.get("candidate_tool_id") or candidate["provisional_candidate_id"],
        "tool_name": candidate["tool_name"],
        "scenario": target["scenario"],
        "core_method": candidate["core_method"],
        "main_input": candidate["main_input"],
        "main_output": candidate["main_output"],
        "lifecycle_status": candidate.get("lifecycle_status", "source_screened_unimplemented"),
    }
    candidate_contract = {
        "supported_systems": candidate["supported_systems"],
        "data_or_model_version": candidate.get("data_or_model_version", "source_version_unfrozen"),
        "service_status": candidate.get("service_status", "implementation_pending"),
    }
    return scoring.score_pair(target, score_row, target_contract, candidate_contract, audit_config)


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    sources = load_sources(config)
    if sources["method_freeze_adoption"]["decision"] != "adopted":
        raise ValueError("development method freeze is not adopted")
    coverage_report = common.load_json(
        WORKSPACE / "outputs/v11_cf05_e3_five_target_pool_coverage_audit_v1_1_20260811/cf05_five_target_pool_coverage_report.json"
    )
    if coverage_report["dose_8_neighbor_ready_target_ids"] != ["A003"]:
        raise ValueError("coverage starting state changed")
    relation_counts = Counter(
        row["relation_type"]
        for row in sources["combined_relation_registry"]["relations"]
        if row["target_tool_id"] == "A004" and row.get("relation_registry_admitted") is True
    )
    if relation_counts != Counter({"lexical": 3, "contract_mismatch": 4}):
        raise ValueError("candidate registry A004 relation counts changed")
    catalog = sources["schema_catalog"]
    target = next(row for row in catalog["entries"] if row["tool_id"] == "A004")
    target_contract = next(row for row in sources["verified_contracts"]["contracts"] if row["tool_id"] == "A004")
    audit_config = sources["neighbor_audit_config"]
    base_lexical = next(
        row for row in common.load_json(WORKSPACE / "outputs/v11_cf05_e3_neighbor_feasibility_v1_1_20260803/neighbor_candidate_matrix.json")["targets"]
        if row["target_tool_id"] == "A004"
    )
    if "A003" not in {row["candidate_tool_id"] for row in base_lexical["lexical_candidates"]}:
        raise ValueError("base A004 lexical relation changed")

    batch3 = {row["candidate_tool_id"]: row for row in sources["batch3_candidate_registry"]["candidates"]}
    reuse = batch3.get("E3C024")
    if not reuse:
        raise ValueError("E3C024 reuse candidate missing")
    reuse_score = score_candidate(reuse, target, target_contract, audit_config)
    if reuse_score["algorithmic_lexical_candidate"] is not True:
        raise ValueError("E3C024 no longer passes the A004 lexical screen")
    reuse_row = {
        "candidate_id": "E3C024",
        "candidate_origin": "existing_executable_cross_target_candidate",
        "intended_relation_type": "lexical",
        "algorithmic_screen_passed": True,
        "runtime_contract_already_passed": reuse.get("runtime_contract_passed") is True,
        "target_specific_relation_review_complete": False,
        "eligible_for_relation_admission": False,
        "score": reuse_score,
    }

    source_rows = []
    for candidate in config["new_source_candidates"]:
        intended = candidate["intended_relation_type"]
        score = score_candidate(candidate, target, target_contract, audit_config)
        threshold = (
            score["algorithmic_lexical_candidate"]
            if intended == "lexical"
            else score["provable_contract_mismatch_neighbor"]
        )
        if not threshold:
            raise ValueError(f"source candidate fails intended deterministic screen: {candidate['provisional_candidate_id']}")
        source_rows.append(
            {
                **candidate,
                "candidate_origin": "official_documented_source_unimplemented",
                "algorithmic_screen_passed": True,
                "score": score,
                "source_snapshot_frozen": False,
                "runtime_contract_passed": False,
                "independence_review_passed": False,
                "target_valid_candidate_invalid_fixture_passed": False,
                "acceptable_equivalent_excluded": False,
                "eligible_for_relation_admission": False,
            }
        )
    intended_counts = Counter([reuse_row["intended_relation_type"], *(row["intended_relation_type"] for row in source_rows)])
    if intended_counts != Counter({"lexical": 4, "functional_overlap": 4}):
        raise ValueError("opening does not provide balanced 4+4 candidate capacity")
    callable_ids = [row["callable_identity"] for row in source_rows]
    if len(callable_ids) != len(set(callable_ids)):
        raise ValueError("new source candidates contain duplicate callable identities")

    screening = {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "target_tool_id": "A004",
        "screened_candidate_count": 8,
        "intended_relation_counts": dict(sorted(intended_counts.items())),
        "rows": [reuse_row, *source_rows],
        "algorithmic_screen_pass_count": 8,
        "relation_admission_count": 0,
    }
    blockers = []
    for row in screening["rows"]:
        candidate_id = row.get("candidate_id") or row["provisional_candidate_id"]
        blockers.append({
            "candidate_id": candidate_id,
            "required_before_admission": (
                ["target_specific_relation_review", "target_valid_candidate_invalid_fixture"]
                if candidate_id == "E3C024"
                else [
                    "freeze_official_source_snapshot", "freeze_package_version",
                    "approve_nonformal_tool_identity", "implement_callable_adapter",
                    "pass_normal_boundary_failure_runtime_cases", "pass_independence_review",
                    "exclude_acceptable_equivalence", "pass_target_valid_candidate_invalid_fixture",
                ]
            ),
            "blocked": True,
        })
    report = {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "status": "balanced_source_capacity_found_implementation_not_authorized",
        "starting_relation_counts": config["starting_relation_counts"],
        "target_relation_counts": config["target_relation_counts"],
        "screened_candidate_count": 8,
        "existing_identity_reuse_candidate_count": 1,
        "new_source_candidate_count": 7,
        "intended_lexical_addition_count": intended_counts["lexical"],
        "intended_functional_addition_count": intended_counts["functional_overlap"],
        "algorithmic_screen_pass_count": 8,
        "independence_review_group_count": len(config["mandatory_independence_review_groups"]),
        "relation_admission_count": 0,
        "new_tool_identities_created": 0,
        "dependencies_installed": 0,
        "local_candidate_executions": 0,
        "external_api_calls": 0,
        "dose8_pools_generated": 0,
        "independent_validation_split_accessed": False,
        "formal_pool_generation_allowed": False,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "next_gate": "approve source snapshot and staged nonformal implementation; review E3C024 first, then implement available-dependency candidates before installing scikit-learn or scikit-bio",
    }
    authorization = {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "decision": "pending_user_authorization",
        "authorized": False,
        "proposed_stage_1": ["E3C024 target-specific review", "SRC-PANDAS-A004-001", "SRC-NUMPY-A004-001", "SRC-SCIPY-A004-002", "SRC-SCIPY-A004-003"],
        "proposed_stage_2": ["SRC-SKLEARN-A004-001", "SRC-SKBIO-A004-001", "SRC-SKBIO-A004-002"],
        "stage_2_requires_dependency_installation": True,
        "external_api_calls_requested": 0,
        "formal_pool_generation_requested": False,
    }
    return {"screening": screening, "blockers": blockers, "report": report, "authorization": authorization}


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = common.load_json(CONFIG_PATH)
    built = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a004_dose8_expansion_config_snapshot.json": config,
        "a004_dose8_source_screening.json": built["screening"],
        "a004_dose8_admission_blockers.json": {"schema_version": "1.0", "rows": built["blockers"]},
        "a004_dose8_expansion_report.json": built["report"],
        "implementation_authorization_request.json": built["authorization"],
    }
    for filename, value in artifacts.items():
        common.write_json(output_dir / filename, value)
    paths = sorted(output_dir.iterdir(), key=lambda path: path.name)
    common.write_json(
        output_dir / "artifact_manifest.json",
        {
            "schema_version": "1.0",
            "opening_id": config["opening_id"],
            "artifact_count": len(paths),
            "artifacts": [
                {"filename": path.name, "sha256": common.file_hash(path), "bytes": path.stat().st_size}
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
