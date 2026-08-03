"""Admit verified E3 candidates to evidence registries without generating formal pools."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("candidate_admission_config_v1.json")


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


def validate_manifest(path: Path, expected_hash: str) -> dict[str, Any]:
    validate_bound_file(path, expected_hash)
    manifest = load_json(path)
    artifacts = manifest["artifacts"]
    if manifest["artifact_count"] != len(artifacts):
        raise ValueError(f"manifest artifact count mismatch: {path}")
    names = [row["filename"] for row in artifacts]
    if len(names) != len(set(names)):
        raise ValueError(f"duplicate artifact filename: {path}")
    for artifact in artifacts:
        artifact_path = path.parent / artifact["filename"]
        validate_bound_file(artifact_path, artifact["sha256"])
        if artifact_path.stat().st_size != artifact["bytes"]:
            raise ValueError(f"artifact byte count mismatch: {artifact_path}")
    return manifest


def manifest_dir(config: dict[str, Any], marker: str) -> Path:
    binding = next(row for row in config["bindings"] if marker in row["path"])
    path = WORKSPACE / binding["path"]
    validate_manifest(path, binding["sha256"])
    return path.parent


def decide(config: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "formal_catalog_mutation_allowed",
        "formal_pool_generation_allowed",
        "external_api_calls_authorized",
        "confirmatory_inference_allowed",
    ):
        if config.get(key) is not False:
            raise ValueError(f"{key} must remain false")
    protocol_binding = next(row for row in config["bindings"] if row["path"].endswith("research_protocol_v1.1-rc1.md"))
    validate_bound_file(WORKSPACE / protocol_binding["path"], protocol_binding["sha256"])

    equivalence_dir = manifest_dir(config, "e3_equivalence_batch1")
    post_review_dir = manifest_dir(config, "e3_post_equivalence_review")
    holdout_dir = manifest_dir(config, "e3_candidate_holdout")
    registration_dir = manifest_dir(config, "e3_registration_candidates")
    expansion_dir = manifest_dir(config, "e3_expansion_plan")

    equivalence_summary = load_json(equivalence_dir / "equivalence_candidate_summary.json")
    independence = load_json(post_review_dir / "acceptable_candidate_independence_review.json")
    holdout_report = load_json(holdout_dir / "candidate_holdout_run_report.json")
    mismatch_holdout = load_json(holdout_dir / "contract_mismatch_holdout_results.json")
    registration_report = load_json(registration_dir / "candidate_registration_report.json")
    registration_registry = load_json(registration_dir / "candidate_registration_registry.json")
    relation_similarity = load_json(registration_dir / "candidate_relation_similarity.json")
    runtime_results = load_json(registration_dir / "candidate_runtime_contract_results.json")
    expansion_report = load_json(expansion_dir / "expansion_plan_report.json")
    expansion_matrix = load_json(expansion_dir / "expansion_requirement_matrix.json")

    required_ids = set(config["required_candidate_ids"])
    registry_by_id = {row["candidate_tool_id"]: row for row in registration_registry["candidates"]}
    relation_by_id = {row["candidate_tool_id"]: row for row in relation_similarity["rows"]}
    runtime_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in runtime_results["rows"]:
        runtime_by_id.setdefault(row["candidate_tool_id"], []).append(row)
    if set(registry_by_id) != required_ids or set(relation_by_id) != required_ids:
        raise ValueError("registration package does not contain exactly the required candidates")
    if registration_report["all_runtime_contracts_passed"] is not True:
        raise ValueError("registration runtime contracts did not all pass")
    if registration_report["relation_candidate_counts"]["evidence_insufficient"] != 0:
        raise ValueError("registration contains evidence-insufficient candidates")

    acceptable_id = config["acceptable_candidate_id"]
    acceptable_registry = registry_by_id[acceptable_id]
    acceptable_relation = relation_by_id[acceptable_id]
    source_equivalence = next(
        row for row in equivalence_summary["candidates"]
        if row["provisional_candidate_id"] == config["acceptable_source_candidate_id"]
    )
    acceptable_checks = {
        "target_matches": acceptable_registry["target_tool_id"] == config["acceptable_target_tool_id"],
        "exact_equivalence_passed": source_equivalence["equivalence_classification"] == "exact_equivalent_over_frozen_scope",
        "implementation_provider_distinct": independence["implementation_provider_distinct"] is True,
        "scientific_function_distinct": independence["scientific_function_distinct"] is True,
        "holdout_runtime_verified": holdout_report["pint_runtime_verification_passed"] is True,
        "registration_runtime_verified": all(row["contract_outcome_pass"] for row in runtime_by_id[acceptable_id]),
        "relation_evidence_passed": acceptable_relation["relation_evidence_passed"] is True,
        "relation_is_acceptable": acceptable_relation["registration_candidate_relation"] == "acceptable_equivalent",
    }
    acceptable_admitted = all(
        value for key, value in acceptable_checks.items() if key != "scientific_function_distinct"
    ) and acceptable_checks["scientific_function_distinct"] is False
    acceptable_decision = {
        "candidate_tool_id": acceptable_id,
        "target_tool_id": config["acceptable_target_tool_id"],
        "checks": acceptable_checks,
        "decision": "admit_to_task_acceptable_tools_registry" if acceptable_admitted else "reject",
        "acceptable_tools_registry_admitted": acceptable_admitted,
        "counts_as_new_scientific_function": False,
        "counts_toward_formal_catalog_size": False,
        "formal_pool_inclusion": False,
    }

    mismatch_by_case = {row["case_id"]: row for row in mismatch_holdout["rows"]}
    neighbor_decisions = []
    used_slots: set[tuple[str, str, str]] = set()
    for candidate_id in sorted(required_ids - {acceptable_id}):
        registry = registry_by_id[candidate_id]
        relation = relation_by_id[candidate_id]
        relation_type = relation["registration_candidate_relation"]
        evidence_ids = relation["relation_evidence_case_ids"]
        evidence_passed = all(
            case_id in mismatch_by_case and mismatch_by_case[case_id]["relation_fixture_pass"]
            for case_id in evidence_ids
        )
        checks = {
            "runtime_contract_passed": all(row["contract_outcome_pass"] for row in runtime_by_id[candidate_id]),
            "relation_evidence_passed": relation["relation_evidence_passed"] is True and evidence_passed,
            "relation_type_allowed": relation_type in config["allowed_neighbor_relation_types"],
            "not_acceptable_equivalent": relation_type != "acceptable_equivalent",
            "single_relation_assigned": bool(relation_type),
        }
        slot_key = (registry["target_tool_id"], relation_type, candidate_id)
        no_duplicate_slot = slot_key not in used_slots
        checks["no_duplicate_slot"] = no_duplicate_slot
        admitted = all(checks.values())
        if admitted:
            used_slots.add(slot_key)
        neighbor_decisions.append(
            {
                "candidate_tool_id": candidate_id,
                "target_tool_id": registry["target_tool_id"],
                "relation_type": relation_type,
                "relation_evidence_case_ids": evidence_ids,
                "checks": checks,
                "decision": "admit_to_relation_evidence_registry" if admitted else "reject",
                "relation_registry_admitted": admitted,
                "formal_pool_inclusion": False,
            }
        )

    if not acceptable_admitted or not all(row["relation_registry_admitted"] for row in neighbor_decisions):
        raise ValueError("one or more required candidate admissions failed")
    if config["one_relation_per_candidate"]:
        admitted_ids = [row["candidate_tool_id"] for row in neighbor_decisions]
        if len(admitted_ids) != len(set(admitted_ids)):
            raise ValueError("candidate admitted to multiple neighbor relations")

    additions = Counter((row["target_tool_id"], row["relation_type"]) for row in neighbor_decisions)
    recalculated_rows = []
    for requirement in expansion_matrix["requirements"]:
        target_id = requirement["target_tool_id"]
        lexical_added = additions[(target_id, "lexical")]
        mismatch_added = additions[(target_id, "contract_mismatch")]
        lexical_count = requirement["current_lexical_count"] + lexical_added
        mismatch_count = requirement["current_contract_mismatch_count"] + mismatch_added
        max_count = config["target_neighbor_count_per_type"]
        if lexical_count > max_count or mismatch_count > max_count:
            raise ValueError(f"admission exceeds target dose capacity: {target_id}")
        recalculated_rows.append(
            {
                "target_tool_id": target_id,
                "target_tool_name": requirement["target_tool_name"],
                "lexical_count_before": requirement["current_lexical_count"],
                "lexical_admitted": lexical_added,
                "lexical_count_after": lexical_count,
                "lexical_gap_to_8_after": max_count - lexical_count,
                "contract_mismatch_count_before": requirement["current_contract_mismatch_count"],
                "contract_mismatch_admitted": mismatch_added,
                "contract_mismatch_count_after": mismatch_count,
                "contract_mismatch_gap_to_8_after": max_count - mismatch_count,
                "paired_8_ready_after": lexical_count >= max_count and mismatch_count >= max_count,
            }
        )
    lexical_gap_after = sum(row["lexical_gap_to_8_after"] for row in recalculated_rows)
    mismatch_gap_after = sum(row["contract_mismatch_gap_to_8_after"] for row in recalculated_rows)
    if expansion_report["lexical_gap_total"] - lexical_gap_after != additions.total() - sum(
        count for (target, relation), count in additions.items() if relation == "contract_mismatch"
    ):
        raise ValueError("lexical gap recomputation mismatch")
    if expansion_report["contract_mismatch_gap_total"] - mismatch_gap_after != sum(
        count for (target, relation), count in additions.items() if relation == "contract_mismatch"
    ):
        raise ValueError("contract mismatch gap recomputation mismatch")

    acceptable_registry_output = {
        "decision_id": config["decision_id"],
        "acceptable_set_count": 1,
        "sets": [
            {
                "target_tool_id": config["acceptable_target_tool_id"],
                "acceptable_tool_ids": [config["acceptable_target_tool_id"], acceptable_id],
                "candidate_scope": "A001_frozen_unit_pair_subset",
                "formal_pool_inclusion": False,
            }
        ],
    }
    relation_registry_output = {
        "decision_id": config["decision_id"],
        "admitted_relation_count": len(neighbor_decisions),
        "relations": neighbor_decisions,
        "formal_pool_inclusion_count": 0,
    }
    gap_output = {
        "decision_id": config["decision_id"],
        "source_plan_id": expansion_report["plan_id"],
        "rows": recalculated_rows,
        "lexical_gap_before": expansion_report["lexical_gap_total"],
        "lexical_admitted": sum(count for (target, relation), count in additions.items() if relation == "lexical"),
        "lexical_gap_after": lexical_gap_after,
        "contract_mismatch_gap_before": expansion_report["contract_mismatch_gap_total"],
        "contract_mismatch_admitted": sum(
            count for (target, relation), count in additions.items() if relation == "contract_mismatch"
        ),
        "contract_mismatch_gap_after": mismatch_gap_after,
    }
    decisions = {
        "decision_id": config["decision_id"],
        "acceptable_decision": acceptable_decision,
        "neighbor_decisions": neighbor_decisions,
    }
    report = {
        "decision_id": config["decision_id"],
        "scope": config["scope"],
        "status": "evidence_registry_admission_complete_formal_pool_pending",
        "acceptable_tools_registry_admission_count": int(acceptable_admitted),
        "neighbor_relation_registry_admission_count": len(neighbor_decisions),
        "lexical_relation_admission_count": gap_output["lexical_admitted"],
        "contract_mismatch_relation_admission_count": gap_output["contract_mismatch_admitted"],
        "scientific_function_catalog_increment_count": 0,
        "formal_catalog_size": registration_report["formal_catalog_size_after"],
        "formal_pool_inclusion_count": 0,
        "lexical_gap_before": gap_output["lexical_gap_before"],
        "lexical_gap_after": lexical_gap_after,
        "contract_mismatch_gap_before": gap_output["contract_mismatch_gap_before"],
        "contract_mismatch_gap_after": mismatch_gap_after,
        "external_api_calls": 0,
        "formal_pool_generation_allowed": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    return {
        "decisions": decisions,
        "acceptable_registry": acceptable_registry_output,
        "relation_registry": relation_registry_output,
        "gap_matrix": gap_output,
        "report": report,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    result = decide(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "candidate_admission_decisions.json": result["decisions"],
        "acceptable_tools_registry_candidate.json": result["acceptable_registry"],
        "relation_evidence_registry.json": result["relation_registry"],
        "recalculated_gap_matrix.json": result["gap_matrix"],
        "candidate_admission_report.json": result["report"],
        "candidate_admission_config_snapshot.json": config,
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    manifest = {
        "decision_id": config["decision_id"],
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
