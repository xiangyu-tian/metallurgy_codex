"""Run the offline pre-admission screen for source-bound E3 candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing.audit_e3_neighbor_feasibility import dice


WORKSPACE = Path(__file__).resolve().parents[3]
POLICY_PATH = Path(__file__).with_name("candidate_screening_policy_v1.json")


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


def screen(policy: dict[str, Any]) -> dict[str, Any]:
    if policy.get("screening_is_final_admission") is not False:
        raise ValueError("screening must not be represented as final admission")
    if policy.get("external_api_calls_authorized") is not False:
        raise ValueError("candidate screening must remain offline")

    registry_path = WORKSPACE / policy["source_registry_path"]
    catalog_path = WORKSPACE / policy["catalog_path"]
    audit_config_path = WORKSPACE / policy["neighbor_audit_config_path"]
    validate_bound_file(registry_path, policy["source_registry_sha256"])
    validate_bound_file(catalog_path, policy["catalog_sha256"])
    validate_bound_file(
        audit_config_path,
        policy["neighbor_audit_config_sha256"],
    )

    registry = load_json(registry_path)
    catalog = load_json(catalog_path)
    audit_config = load_json(audit_config_path)
    candidates = registry["candidates"]
    catalog_by_id = {entry["tool_id"]: entry for entry in catalog["entries"]}
    candidate_ids = {row["provisional_candidate_id"] for row in candidates}
    decisions = policy["decisions"]
    decision_ids = [row["provisional_candidate_id"] for row in decisions]
    if len(decision_ids) != len(set(decision_ids)):
        raise ValueError("duplicate candidate screening decision")
    if set(decision_ids) != candidate_ids:
        raise ValueError("screening decisions must cover the source registry exactly")

    allowed_lanes = set(policy["allowed_lanes"])
    decision_by_id = {row["provisional_candidate_id"]: row for row in decisions}
    lane_counts: Counter[str] = Counter()
    target_queue_counts: Counter[str] = Counter()
    target_alias_pass_counts: Counter[str] = Counter()
    lane_ids: defaultdict[str, list[str]] = defaultdict(list)
    rows = []
    threshold = audit_config["lexical_name_dice_min"]
    for candidate in candidates:
        decision = decision_by_id[candidate["provisional_candidate_id"]]
        lane = decision["screening_lane"]
        if lane not in allowed_lanes:
            raise ValueError(f"invalid screening lane: {lane}")
        if not decision.get("rationale") or not decision.get("independence_class"):
            raise ValueError("screening decisions require rationale and independence class")
        matches = decision.get("existing_catalog_matches", [])
        if not matches or any(tool_id not in catalog_by_id for tool_id in matches):
            raise ValueError(
                f"unknown or empty catalog match for {candidate['provisional_candidate_id']}"
            )
        target_id = candidate["target_tool_id"]
        target_alias = catalog_by_id[target_id]["semantic_alias"]
        alias_score = round(dice(target_alias, candidate["capability_name"]), 6)
        raw_alias_pass = alias_score >= threshold
        in_contract_queue = lane == "contract_draft_queue"
        alias_review_pass = in_contract_queue and raw_alias_pass
        lane_counts[lane] += 1
        lane_ids[lane].append(candidate["provisional_candidate_id"])
        if in_contract_queue:
            target_queue_counts[target_id] += 1
        if alias_review_pass:
            target_alias_pass_counts[target_id] += 1
        rows.append(
            {
                "provisional_candidate_id": candidate["provisional_candidate_id"],
                "capability_name": candidate["capability_name"],
                "package": candidate["package"],
                "target_tool_id": target_id,
                "target_semantic_alias": target_alias,
                "source_ids": candidate["source_ids"],
                "screening_lane": lane,
                "independence_class": decision["independence_class"],
                "existing_catalog_matches": matches,
                "rationale": decision["rationale"],
                "alias_name_bigram_dice": alias_score,
                "lexical_name_dice_min": threshold,
                "raw_alias_name_threshold_pass": raw_alias_pass,
                "may_enter_contract_draft": in_contract_queue,
                "preliminary_lexical_name_review_pass": alias_review_pass,
                "full_contract_text_score": None,
                "semantic_equivalence_test_passed": None,
                "independence_evidence_passed": None,
                "target_valid_candidate_invalid_fixture_passed": None,
                "admitted_to_catalog": False,
                "may_fill_relation_slot": False,
            }
        )

    summary = {
        "screening_id": policy["screening_id"],
        "status": "pre_admission_screen_complete_followup_evidence_required",
        "candidate_count": len(candidates),
        "screening_lane_counts": {
            lane: lane_counts[lane] for lane in policy["allowed_lanes"]
        },
        "screening_lane_candidate_ids": {
            lane: lane_ids[lane] for lane in policy["allowed_lanes"]
        },
        "contract_draft_queue_count_by_target": dict(sorted(target_queue_counts.items())),
        "preliminary_alias_name_pass_count": sum(target_alias_pass_counts.values()),
        "preliminary_alias_name_pass_count_by_target": dict(
            sorted(target_alias_pass_counts.items())
        ),
        "full_contract_text_score_complete_count": 0,
        "equivalence_test_complete_count": 0,
        "equivalence_test_pass_count": 0,
        "independence_review_complete_count": 0,
        "independence_evidence_pass_count": 0,
        "relation_fixture_complete_count": 0,
        "relation_fixture_pass_count": 0,
        "accepted_candidate_count": 0,
        "catalog_increment_count": 0,
        "filled_relation_slot_count": 0,
        "remaining_lexical_gap": 30,
        "remaining_contract_mismatch_gap": 40,
        "external_api_calls": 0,
        "formal_pool_generation_allowed": False,
        "core_frozen": False,
        "next_gate": (
            "draft complete callable contracts for contract_draft_queue entries; "
            "run equivalence tests separately; then build target-valid/candidate-invalid fixtures"
        ),
    }
    binding_report = {
        "screening_id": policy["screening_id"],
        "source_registry": {
            "path": policy["source_registry_path"],
            "sha256": policy["source_registry_sha256"],
        },
        "catalog": {
            "path": policy["catalog_path"],
            "sha256": policy["catalog_sha256"],
        },
        "neighbor_audit_config": {
            "path": policy["neighbor_audit_config_path"],
            "sha256": policy["neighbor_audit_config_sha256"],
        },
        "all_bindings_passed": True,
        "external_api_calls": 0,
    }
    return {
        "screening_matrix": {
            "screening_id": policy["screening_id"],
            "candidate_count": len(rows),
            "rows": rows,
        },
        "summary": summary,
        "binding_report": binding_report,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    policy = load_json(POLICY_PATH)
    result = screen(policy)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "candidate_screening_matrix.json": result["screening_matrix"],
        "candidate_screening_summary.json": result["summary"],
        "source_binding_report.json": result["binding_report"],
        "candidate_screening_policy_snapshot.json": policy,
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    manifest = {
        "screening_id": policy["screening_id"],
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
    return result["summary"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    report = build_outputs(Path(args.output_dir).resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
