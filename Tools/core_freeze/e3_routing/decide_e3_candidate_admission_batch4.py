"""Admit batch-4 A004 relations to nonformal evidence, never to formal pools."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing.decide_e3_candidate_admission_batch3 import (
    binding,
    load_json,
    sha256_file,
    validate_manifest,
    write_json,
)


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("candidate_admission_batch4_config_v1.json")


def decide(config: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "formal_catalog_mutation_allowed",
        "formal_pool_generation_allowed",
        "external_api_calls_authorized",
        "confirmatory_inference_allowed",
    ):
        if config.get(key) is not False:
            raise ValueError(f"{key} must remain false")
    registration_binding = binding(config, "batch4_registration")
    prior_binding = binding(config, "batch3_admission")
    validate_manifest(WORKSPACE / registration_binding["path"], registration_binding["sha256"])
    validate_manifest(WORKSPACE / prior_binding["path"], prior_binding["sha256"])
    registration_dir = (WORKSPACE / registration_binding["path"]).parent
    prior_dir = (WORKSPACE / prior_binding["path"]).parent

    registry = load_json(registration_dir / "candidate_registration_registry.json")
    runtime = load_json(registration_dir / "candidate_runtime_contract_results.json")
    relations = load_json(registration_dir / "candidate_relation_evidence.json")
    independence = load_json(registration_dir / "candidate_independence_matrix.json")
    registration_report = load_json(registration_dir / "candidate_registration_report.json")
    prior_relations = load_json(prior_dir / "combined_relation_evidence_registry.json")
    prior_gap = load_json(prior_dir / "recalculated_gap_matrix.json")
    prior_acceptable = load_json(prior_dir / "acceptable_tools_registry_carried_forward.json")

    required_ids = set(config["required_candidate_ids"])
    registry_by_id = {row["candidate_tool_id"]: row for row in registry["candidates"]}
    relation_by_id = {row["candidate_tool_id"]: row for row in relations["rows"]}
    independence_by_id = {row["candidate_tool_id"]: row for row in independence["rows"]}
    runtime_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in runtime["rows"]:
        runtime_by_id.setdefault(row["candidate_tool_id"], []).append(row)
    if any(set(rows) != required_ids for rows in (registry_by_id, relation_by_id, independence_by_id, runtime_by_id)):
        raise ValueError("batch-4 package does not contain exactly the required candidate IDs")
    if registration_report["all_runtime_contracts_passed"] is not True:
        raise ValueError("batch-4 runtime contracts did not all pass")
    if registration_report["a004_paired_4_ready_if_admitted"] is not True:
        raise ValueError("registration report does not support A004 paired-4 readiness")
    if len({row["callable_identity"] for row in independence_by_id.values()}) != len(required_ids):
        raise ValueError("batch-4 callable identities are not unique")

    decisions = []
    additions: Counter[tuple[str, str]] = Counter()
    for candidate_id in config["required_candidate_ids"]:
        candidate = registry_by_id[candidate_id]
        relation = relation_by_id[candidate_id]
        relation_type = relation["registration_candidate_relation"]
        target_id = candidate["target_tool_id"]
        checks = {
            "target_is_a004": target_id == config["required_target_tool_id"],
            "runtime_contract_passed": all(row["contract_outcome_pass"] for row in runtime_by_id[candidate_id]),
            "normal_boundary_failure_present": {row["case_kind"] for row in runtime_by_id[candidate_id]} == {"normal", "boundary", "failure"},
            "relation_evidence_passed": relation["relation_evidence_passed"] is True,
            "relation_type_allowed": relation_type in config["allowed_relation_types"],
            "frozen_threshold_passed": (
                relation["algorithmic_lexical_candidate"] is True
                if relation_type == "lexical"
                else relation["provable_contract_mismatch_neighbor"] is True
            ),
            "independent_callable": independence_by_id[candidate_id]["same_callable_renaming"] is False,
            "distinct_contract": independence_by_id[candidate_id]["distinct_input_or_output_contract"] is True,
            "formal_pool_inclusion_disabled": candidate["formal_pool_inclusion_allowed"] is False,
        }
        if not all(checks.values()):
            raise ValueError(f"candidate evidence admission failed: {candidate_id}")
        additions[(target_id, relation_type)] += 1
        decisions.append(
            {
                "candidate_tool_id": candidate_id,
                "target_tool_id": target_id,
                "relation_type": relation_type,
                "relation_mechanism": relation["relation_mechanism"],
                "callable_identity": candidate["callable_identity"],
                "runtime_evidence_case_ids": relation["runtime_evidence_case_ids"],
                "checks": checks,
                "decision": "admit_to_relation_evidence_registry",
                "relation_registry_admitted": True,
                "formal_pool_inclusion": False,
            }
        )
    if config["one_relation_per_candidate"] and len(decisions) != len({row["candidate_tool_id"] for row in decisions}):
        raise ValueError("candidate admitted to more than one relation")
    observed_counts = Counter(row["relation_type"] for row in decisions)
    if dict(observed_counts) != config["required_relation_counts"]:
        raise ValueError("admitted relation counts do not match the frozen batch-4 dose")

    maximum = config["target_neighbor_count_per_type"]
    gap_rows = []
    for row in prior_gap["rows"]:
        target_id = row["target_tool_id"]
        lexical_added = additions[(target_id, "lexical")]
        mismatch_added = additions[(target_id, "contract_mismatch")]
        lexical_after = row["lexical_count_after"] + lexical_added
        mismatch_after = row["contract_mismatch_count_after"] + mismatch_added
        if lexical_after > maximum or mismatch_after > maximum:
            raise ValueError(f"batch-4 relation exceeds target capacity: {target_id}")
        gap_rows.append(
            {
                "target_tool_id": target_id,
                "target_tool_name": row["target_tool_name"],
                "lexical_count_before": row["lexical_count_after"],
                "lexical_admitted": lexical_added,
                "lexical_count_after": lexical_after,
                "lexical_gap_to_8_after": maximum - lexical_after,
                "contract_mismatch_count_before": row["contract_mismatch_count_after"],
                "contract_mismatch_admitted": mismatch_added,
                "contract_mismatch_count_after": mismatch_after,
                "contract_mismatch_gap_to_8_after": maximum - mismatch_after,
                "paired_4_ready_after": lexical_after >= 4 and mismatch_after >= 4,
                "paired_8_ready_after": lexical_after >= maximum and mismatch_after >= maximum,
            }
        )
    lexical_added_total = sum(value for (_, relation), value in additions.items() if relation == "lexical")
    mismatch_added_total = sum(value for (_, relation), value in additions.items() if relation == "contract_mismatch")
    lexical_gap_after = sum(row["lexical_gap_to_8_after"] for row in gap_rows)
    mismatch_gap_after = sum(row["contract_mismatch_gap_to_8_after"] for row in gap_rows)
    if lexical_gap_after != prior_gap["lexical_gap_after"] - lexical_added_total:
        raise ValueError("batch-4 lexical gap recomputation mismatch")
    if mismatch_gap_after != prior_gap["contract_mismatch_gap_after"] - mismatch_added_total:
        raise ValueError("batch-4 mismatch gap recomputation mismatch")
    a004_gap = next(row for row in gap_rows if row["target_tool_id"] == "A004")
    if not a004_gap["paired_4_ready_after"] or a004_gap["paired_8_ready_after"]:
        raise ValueError("A004 must reach paired-4 but not paired-8 after batch 4")

    combined_relations = list(prior_relations["relations"]) + decisions
    if len(combined_relations) != len({row["candidate_tool_id"] for row in combined_relations}):
        raise ValueError("combined relation registry contains duplicate candidates")
    gap = {
        "decision_id": config["decision_id"],
        "rows": gap_rows,
        "lexical_gap_before": prior_gap["lexical_gap_after"],
        "lexical_admitted": lexical_added_total,
        "lexical_gap_after": lexical_gap_after,
        "contract_mismatch_gap_before": prior_gap["contract_mismatch_gap_after"],
        "contract_mismatch_admitted": mismatch_added_total,
        "contract_mismatch_gap_after": mismatch_gap_after,
        "paired_4_ready_target_ids": [row["target_tool_id"] for row in gap_rows if row["paired_4_ready_after"]],
        "paired_8_ready_target_ids": [row["target_tool_id"] for row in gap_rows if row["paired_8_ready_after"]],
    }
    report = {
        "decision_id": config["decision_id"],
        "scope": config["scope"],
        "status": "batch4_evidence_admitted_a004_paired4_ready_nonformal",
        "batch4_relation_admission_count": len(decisions),
        "combined_relation_registry_count": len(combined_relations),
        "lexical_relation_admission_count": lexical_added_total,
        "contract_mismatch_relation_admission_count": mismatch_added_total,
        "lexical_gap_before": gap["lexical_gap_before"],
        "lexical_gap_after": lexical_gap_after,
        "contract_mismatch_gap_before": gap["contract_mismatch_gap_before"],
        "contract_mismatch_gap_after": mismatch_gap_after,
        "a004_paired_4_ready": True,
        "a004_paired_8_ready": False,
        "paired_4_ready_target_ids": gap["paired_4_ready_target_ids"],
        "paired_8_ready_target_ids": gap["paired_8_ready_target_ids"],
        "acceptable_tools_registry_unchanged": True,
        "scientific_function_catalog_increment_count": 0,
        "formal_catalog_size": registration_report["formal_catalog_size"],
        "formal_pool_inclusion_count": 0,
        "external_api_calls": 0,
        "formal_pool_generation_allowed": False,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
    }
    return {
        "decisions": {"decision_id": config["decision_id"], "admitted": decisions},
        "combined_relations": {
            "decision_id": config["decision_id"],
            "relation_count": len(combined_relations),
            "relations": combined_relations,
            "formal_pool_inclusion_count": 0,
        },
        "acceptable": {**prior_acceptable, "carried_forward_by_decision_id": config["decision_id"]},
        "gap": gap,
        "report": report,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    result = decide(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "candidate_admission_decisions.json": result["decisions"],
        "combined_relation_evidence_registry.json": result["combined_relations"],
        "acceptable_tools_registry_carried_forward.json": result["acceptable"],
        "recalculated_gap_matrix.json": result["gap"],
        "candidate_admission_report.json": result["report"],
        "candidate_admission_config_snapshot.json": config,
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    manifest = {
        "decision_id": config["decision_id"],
        "artifact_count": len(artifacts),
        "artifacts": [
            {"filename": filename, "sha256": sha256_file(output_dir / filename), "bytes": (output_dir / filename).stat().st_size}
            for filename in sorted(artifacts)
        ],
    }
    write_json(output_dir / "artifact_manifest.json", manifest)
    return result["report"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    print(json.dumps(build_outputs(Path(args.output_dir).resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
