"""Admit batch-2 E3 relations to evidence registries, never to formal pools."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("candidate_admission_batch2_config_v1.json")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_bound_file(path: Path, expected_hash: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256_file(path)
    if actual != expected_hash.lower():
        raise ValueError(f"bound file hash mismatch for {path}: {actual}")


def validate_manifest(path: Path, expected_hash: str) -> dict[str, Any]:
    validate_bound_file(path, expected_hash)
    manifest = load_json(path)
    if manifest["artifact_count"] != len(manifest["artifacts"]):
        raise ValueError("manifest artifact count mismatch")
    names = [row["filename"] for row in manifest["artifacts"]]
    if len(names) != len(set(names)):
        raise ValueError("manifest contains duplicate filenames")
    for row in manifest["artifacts"]:
        artifact = path.parent / row["filename"]
        validate_bound_file(artifact, row["sha256"])
        if artifact.stat().st_size != row["bytes"]:
            raise ValueError(f"artifact byte mismatch: {artifact}")
    return manifest


def decide(config: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "formal_catalog_mutation_allowed",
        "formal_pool_generation_allowed",
        "external_api_calls_authorized",
        "confirmatory_inference_allowed",
    ):
        if config.get(key) is not False:
            raise ValueError(f"{key} must remain false")
    binding_by_marker = {"batch2": config["bindings"][0], "batch1": config["bindings"][1]}
    for row in binding_by_marker.values():
        validate_manifest(WORKSPACE / row["path"], row["sha256"])
    batch2_dir = (WORKSPACE / binding_by_marker["batch2"]["path"]).parent
    batch1_dir = (WORKSPACE / binding_by_marker["batch1"]["path"]).parent

    registry = load_json(batch2_dir / "candidate_registration_registry.json")
    runtime = load_json(batch2_dir / "candidate_runtime_contract_results.json")
    relations = load_json(batch2_dir / "candidate_relation_evidence.json")
    blocked = load_json(batch2_dir / "blocked_candidate_registry.json")
    registration_report = load_json(batch2_dir / "candidate_registration_report.json")
    prior_relations = load_json(batch1_dir / "relation_evidence_registry.json")
    prior_gap = load_json(batch1_dir / "recalculated_gap_matrix.json")
    prior_acceptable = load_json(batch1_dir / "acceptable_tools_registry_candidate.json")

    required_ids = set(config["required_candidate_ids"])
    held_ids = set(config["required_relation_held_candidate_ids"])
    registry_by_id = {row["candidate_tool_id"]: row for row in registry["candidates"]}
    relation_by_id = {row["candidate_tool_id"]: row for row in relations["rows"]}
    runtime_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in runtime["rows"]:
        runtime_by_id.setdefault(row["candidate_tool_id"], []).append(row)
    implemented_ids = required_ids | held_ids
    if set(registry_by_id) != implemented_ids or set(relation_by_id) != implemented_ids or set(runtime_by_id) != implemented_ids:
        raise ValueError("batch-2 package does not contain exactly the required implemented candidates")
    blocked_ids = {row["candidate_tool_id"] for row in blocked["candidates"]}
    if blocked_ids != set(config["required_blocked_candidate_ids"]):
        raise ValueError("blocked pycalphad candidate set mismatch")
    if registration_report["all_runtime_contracts_passed"] is not True:
        raise ValueError("batch-2 runtime contracts did not all pass")
    relation_held_decisions = []
    for candidate_id in sorted(held_ids):
        candidate = registry_by_id[candidate_id]
        relation = relation_by_id[candidate_id]
        if not all(row["contract_outcome_pass"] for row in runtime_by_id[candidate_id]):
            raise ValueError(f"relation-held candidate runtime failed: {candidate_id}")
        if relation["registration_candidate_relation"] != "evidence_insufficient":
            raise ValueError(f"relation-held candidate unexpectedly passed: {candidate_id}")
        relation_held_decisions.append(
            {
                "candidate_tool_id": candidate_id,
                "target_tool_id": candidate["target_tool_id"],
                "proposed_relation_type": relation["relation_policy"],
                "decision": "hold_relation_evidence_insufficient",
                "runtime_contract_passed": True,
                "relation_registry_admitted": False,
                "formal_pool_inclusion": False,
            }
        )

    decisions = []
    additions: Counter[tuple[str, str]] = Counter()
    for candidate_id in config["required_candidate_ids"]:
        candidate = registry_by_id[candidate_id]
        relation = relation_by_id[candidate_id]
        relation_type = relation["registration_candidate_relation"]
        checks = {
            "runtime_contract_passed": all(row["contract_outcome_pass"] for row in runtime_by_id[candidate_id]),
            "normal_boundary_failure_present": {row["case_kind"] for row in runtime_by_id[candidate_id]} == {"normal", "boundary", "failure"},
            "relation_evidence_passed": relation["relation_evidence_passed"] is True,
            "relation_type_allowed": relation_type in config["allowed_relation_types"],
            "frozen_threshold_passed": (
                relation["algorithmic_lexical_candidate"] is True
                if relation_type == "lexical"
                else relation["provable_contract_mismatch_neighbor"] is True
            ),
            "formal_pool_inclusion_disabled": candidate["formal_pool_inclusion_allowed"] is False,
        }
        admitted = all(checks.values())
        if not admitted:
            raise ValueError(f"candidate evidence admission failed: {candidate_id}")
        additions[(candidate["target_tool_id"], relation_type)] += 1
        decisions.append(
            {
                "candidate_tool_id": candidate_id,
                "target_tool_id": candidate["target_tool_id"],
                "relation_type": relation_type,
                "relation_mechanism": relation["relation_mechanism"],
                "runtime_evidence_case_ids": relation["runtime_evidence_case_ids"],
                "checks": checks,
                "decision": "admit_to_relation_evidence_registry",
                "relation_registry_admitted": True,
                "formal_pool_inclusion": False,
            }
        )
    if config["one_relation_per_candidate"] and len(decisions) != len({row["candidate_tool_id"] for row in decisions}):
        raise ValueError("candidate admitted to more than one relation")

    gap_rows = []
    for row in prior_gap["rows"]:
        target_id = row["target_tool_id"]
        lexical_added = additions[(target_id, "lexical")]
        mismatch_added = additions[(target_id, "contract_mismatch")]
        lexical_after = row["lexical_count_after"] + lexical_added
        mismatch_after = row["contract_mismatch_count_after"] + mismatch_added
        maximum = config["target_neighbor_count_per_type"]
        if lexical_after > maximum or mismatch_after > maximum:
            raise ValueError(f"batch-2 relation exceeds target capacity: {target_id}")
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
                "paired_8_ready_after": lexical_after >= maximum and mismatch_after >= maximum,
            }
        )
    lexical_added_total = sum(value for (target, relation), value in additions.items() if relation == "lexical")
    mismatch_added_total = sum(value for (target, relation), value in additions.items() if relation == "contract_mismatch")
    lexical_after_total = sum(row["lexical_gap_to_8_after"] for row in gap_rows)
    mismatch_after_total = sum(row["contract_mismatch_gap_to_8_after"] for row in gap_rows)
    if lexical_after_total != prior_gap["lexical_gap_after"] - lexical_added_total:
        raise ValueError("batch-2 lexical gap recomputation mismatch")
    if mismatch_after_total != prior_gap["contract_mismatch_gap_after"] - mismatch_added_total:
        raise ValueError("batch-2 contract mismatch gap recomputation mismatch")

    combined_relations = list(prior_relations["relations"]) + decisions
    if len(combined_relations) != len({row["candidate_tool_id"] for row in combined_relations}):
        raise ValueError("combined relation registry contains duplicate candidates")
    blocked_decisions = [
        {
            **row,
            "decision": "hold_until_scientific_asset_frozen",
            "relation_registry_admitted": False,
            "formal_pool_inclusion": False,
        }
        for row in blocked["candidates"]
    ]
    gap = {
        "decision_id": config["decision_id"],
        "rows": gap_rows,
        "lexical_gap_before": prior_gap["lexical_gap_after"],
        "lexical_admitted": lexical_added_total,
        "lexical_gap_after": lexical_after_total,
        "contract_mismatch_gap_before": prior_gap["contract_mismatch_gap_after"],
        "contract_mismatch_admitted": mismatch_added_total,
        "contract_mismatch_gap_after": mismatch_after_total,
    }
    report = {
        "decision_id": config["decision_id"],
        "scope": config["scope"],
        "status": "batch2_evidence_admitted_pycalphad_held_formal_pool_pending",
        "batch2_relation_admission_count": len(decisions),
        "relation_evidence_held_count": len(relation_held_decisions),
        "combined_relation_registry_count": len(combined_relations),
        "blocked_candidate_count": len(blocked_decisions),
        "lexical_relation_admission_count": lexical_added_total,
        "contract_mismatch_relation_admission_count": mismatch_added_total,
        "lexical_gap_before": gap["lexical_gap_before"],
        "lexical_gap_after": lexical_after_total,
        "contract_mismatch_gap_before": gap["contract_mismatch_gap_before"],
        "contract_mismatch_gap_after": mismatch_after_total,
        "acceptable_tools_registry_unchanged": True,
        "scientific_function_catalog_increment_count": 0,
        "formal_catalog_size": registration_report["formal_catalog_size"],
        "formal_pool_inclusion_count": 0,
        "external_api_calls": 0,
        "formal_pool_generation_allowed": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    return {
        "decisions": {"decision_id": config["decision_id"], "admitted": decisions, "relation_held": relation_held_decisions, "blocked": blocked_decisions},
        "combined_relations": {"decision_id": config["decision_id"], "relation_count": len(combined_relations), "relations": combined_relations, "formal_pool_inclusion_count": 0},
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    print(json.dumps(build_outputs(Path(args.output_dir).resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
