"""Build offline contract drafts and equivalence-test plans for E3 candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing.audit_e3_neighbor_feasibility import dice


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("candidate_contract_package_config_v1.json")


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


def _structured_text(alias: str, inputs: list[str], outputs: list[str]) -> str:
    return " ".join([alias, *sorted(inputs), *sorted(outputs)])


def build_package(config: dict[str, Any]) -> dict[str, Any]:
    bindings = {
        "screening_matrix": (
            config["screening_matrix_path"],
            config["screening_matrix_sha256"],
        ),
        "catalog": (config["catalog_path"], config["catalog_sha256"]),
        "verified_contracts": (
            config["verified_contracts_path"],
            config["verified_contracts_sha256"],
        ),
        "reference_cases": (
            config["reference_cases_path"],
            config["reference_cases_sha256"],
        ),
        "neighbor_audit_config": (
            config["neighbor_audit_config_path"],
            config["neighbor_audit_config_sha256"],
        ),
    }
    for path_text, expected_hash in bindings.values():
        validate_bound_file(WORKSPACE / path_text, expected_hash)

    screening = load_json(WORKSPACE / config["screening_matrix_path"])
    catalog = load_json(WORKSPACE / config["catalog_path"])
    verified_contracts = load_json(WORKSPACE / config["verified_contracts_path"])
    reference_cases = load_json(WORKSPACE / config["reference_cases_path"])
    neighbor_config = load_json(WORKSPACE / config["neighbor_audit_config_path"])
    screening_by_id = {
        row["provisional_candidate_id"]: row for row in screening["rows"]
    }
    contract_queue_ids = {
        row["provisional_candidate_id"]
        for row in screening["rows"]
        if row["screening_lane"] == "contract_draft_queue"
    }
    equivalence_queue_ids = {
        row["provisional_candidate_id"]
        for row in screening["rows"]
        if row["screening_lane"] == "equivalence_test_required"
    }
    contract_ids = [row["provisional_candidate_id"] for row in config["contracts"]]
    equivalence_ids = [
        row["provisional_candidate_id"] for row in config["equivalence_tests"]
    ]
    if len(contract_ids) != len(set(contract_ids)) or set(contract_ids) != contract_queue_ids:
        raise ValueError("contract drafts must cover the contract_draft_queue exactly")
    if len(equivalence_ids) != len(set(equivalence_ids)) or set(equivalence_ids) != equivalence_queue_ids:
        raise ValueError("equivalence tests must cover the equivalence queue exactly")

    policy = config["policy"]
    expected_policy = {
        "draft_status": "structurally_complete_execution_unverified",
        "version_lock_status": "pending_dependency_installation_and_lock",
        "implementation_status": "not_implemented",
        "execution_allowed": False,
        "admission_allowed": False,
        "external_api_calls_authorized": False,
        "dependency_installation_authorized": False,
    }
    if policy != expected_policy:
        raise ValueError("contract package must remain non-executable and non-admitting")
    if any(config["dependency_snapshot"]["imports"].values()):
        raise ValueError("dependency snapshot changed; rebuild under a new package version")

    catalog_by_id = {row["tool_id"]: row for row in catalog["entries"]}
    verified_by_id = {
        row["tool_id"]: row for row in verified_contracts["contracts"]
    }
    reference_by_id = {row["case_id"]: row for row in reference_cases["cases"]}
    if len(reference_by_id) != len(reference_cases["cases"]):
        raise ValueError("duplicate verified reference case ID")

    enriched_contracts = []
    similarity_rows = []
    target_counts: Counter[str] = Counter()
    contract_threshold = neighbor_config["lexical_contract_text_dice_min"]
    name_threshold = neighbor_config["lexical_name_dice_min"]
    for contract in config["contracts"]:
        candidate_id = contract["provisional_candidate_id"]
        screen_row = screening_by_id[candidate_id]
        if contract["target_tool_id"] != screen_row["target_tool_id"]:
            raise ValueError(f"target mismatch for {candidate_id}")
        if contract["package"] != screen_row["package"]:
            raise ValueError(f"package mismatch for {candidate_id}")
        required_fields = (
            "semantic_alias",
            "source_operation",
            "scientific_function",
            "input_contract",
            "output_contract",
            "applicability_contract",
            "error_codes",
            "known_limitations",
        )
        if any(not contract.get(field) for field in required_fields):
            raise ValueError(f"incomplete contract draft for {candidate_id}")
        input_contract = contract["input_contract"]
        output_contract = contract["output_contract"]
        if not input_contract.get("parameters") or not input_contract.get("required"):
            raise ValueError(f"missing input parameters for {candidate_id}")
        if not set(input_contract["required"]) <= set(input_contract["parameters"]):
            raise ValueError(f"unknown required input for {candidate_id}")
        if not output_contract.get("properties") or "units" not in output_contract:
            raise ValueError(f"missing output properties or units for {candidate_id}")
        applicability = contract["applicability_contract"]
        if any(not applicability.get(field) for field in ("systems", "prerequisites", "exclusions")):
            raise ValueError(f"incomplete applicability contract for {candidate_id}")
        if contract["import_name"] not in config["dependency_snapshot"]["imports"]:
            raise ValueError(f"untracked dependency import for {candidate_id}")

        target_id = contract["target_tool_id"]
        target_contract = verified_by_id[target_id]
        target_alias = catalog_by_id[target_id]["semantic_alias"]
        target_text = _structured_text(
            target_alias,
            target_contract["required_inputs"] + target_contract["optional_inputs"],
            list(target_contract["output_contract"]),
        )
        candidate_text = _structured_text(
            contract["semantic_alias"],
            list(input_contract["parameters"]),
            list(output_contract["properties"]),
        )
        name_score = round(dice(target_alias, contract["semantic_alias"]), 6)
        contract_score = round(dice(target_text, candidate_text), 6)
        target_counts[target_id] += 1
        similarity_rows.append(
            {
                "provisional_candidate_id": candidate_id,
                "target_tool_id": target_id,
                "target_semantic_alias": target_alias,
                "candidate_semantic_alias": contract["semantic_alias"],
                "name_bigram_dice": name_score,
                "structured_contract_bigram_dice": contract_score,
                "name_threshold": name_threshold,
                "contract_text_threshold": contract_threshold,
                "name_threshold_pass": name_score >= name_threshold,
                "structured_contract_threshold_pass": contract_score >= contract_threshold,
                "final_lexical_relation_pass": False,
                "final_contract_mismatch_relation_pass": False,
                "reason_final_false": "execution, independence, equivalence, and target-valid/candidate-invalid fixtures are pending",
            }
        )
        enriched_contracts.append(
            {
                **contract,
                "source_ids": screen_row["source_ids"],
                "draft_status": policy["draft_status"],
                "version_lock_status": policy["version_lock_status"],
                "implementation_status": policy["implementation_status"],
                "dependency_import_available": config["dependency_snapshot"]["imports"][contract["import_name"]],
                "execution_allowed": False,
                "admission_allowed": False,
                "independence_evidence_passed": None,
                "relation_fixture_passed": None,
            }
        )

    equivalence_plans = []
    used_reference_ids = set()
    for test in config["equivalence_tests"]:
        candidate_id = test["provisional_candidate_id"]
        screen_row = screening_by_id[candidate_id]
        if test["target_tool_id"] != screen_row["target_tool_id"]:
            raise ValueError(f"equivalence target mismatch for {candidate_id}")
        overlap = test["overlap_reference_case_ids"]
        boundary = test["boundary_reference_case_ids"]
        if not overlap or not boundary or set(overlap) & set(boundary):
            raise ValueError(f"invalid reference case split for {candidate_id}")
        for case_id in [*overlap, *boundary]:
            if case_id not in reference_by_id:
                raise ValueError(f"unknown reference case: {case_id}")
            if reference_by_id[case_id]["tool_id"] != test["target_tool_id"]:
                raise ValueError(f"reference target mismatch: {case_id}")
            used_reference_ids.add(case_id)
        equivalence_plans.append(
            {
                **test,
                "source_ids": screen_row["source_ids"],
                "execution_status": "not_started_dependency_unavailable",
                "observed_case_results": None,
                "equivalence_classification": None,
                "may_enter_acceptable_tool_set": False,
                "may_enter_unacceptable_neighbor_set": False,
            }
        )

    structural_count = len(enriched_contracts)
    summary = {
        "package_id": config["package_id"],
        "status": "contract_and_equivalence_design_complete_execution_pending",
        "contract_draft_count": structural_count,
        "contract_draft_count_by_target": dict(sorted(target_counts.items())),
        "structurally_complete_contract_count": structural_count,
        "dependency_import_available_count": 0,
        "version_locked_contract_count": 0,
        "implemented_contract_count": 0,
        "execution_verified_contract_count": 0,
        "independence_verified_contract_count": 0,
        "admission_ready_contract_count": 0,
        "equivalence_test_plan_count": len(equivalence_plans),
        "equivalence_reference_case_count": len(used_reference_ids),
        "equivalence_test_executed_count": 0,
        "equivalence_classified_count": 0,
        "name_threshold_pass_count": sum(row["name_threshold_pass"] for row in similarity_rows),
        "structured_contract_threshold_pass_count": sum(
            row["structured_contract_threshold_pass"] for row in similarity_rows
        ),
        "final_lexical_relation_pass_count": 0,
        "final_contract_mismatch_relation_pass_count": 0,
        "catalog_increment_count": 0,
        "filled_relation_slot_count": 0,
        "remaining_lexical_gap": 30,
        "remaining_contract_mismatch_gap": 40,
        "dependency_installations": 0,
        "external_api_calls": 0,
        "formal_pool_generation_allowed": False,
        "core_frozen": False,
    }
    return {
        "contract_drafts": {
            "package_id": config["package_id"],
            "contract_count": len(enriched_contracts),
            "contracts": enriched_contracts,
        },
        "similarity": {
            "package_id": config["package_id"],
            "method": "character-bigram Dice over frozen semantic aliases and structured input/output field names",
            "rows": similarity_rows,
        },
        "equivalence_plan": {
            "package_id": config["package_id"],
            "test_plan_count": len(equivalence_plans),
            "tests": equivalence_plans,
        },
        "environment": {
            "package_id": config["package_id"],
            **config["dependency_snapshot"],
            "dependency_installation_authorized": False,
            "execution_allowed": False,
        },
        "bindings": {
            "package_id": config["package_id"],
            "all_bindings_passed": True,
            "bindings": [
                {"name": name, "path": path, "sha256": digest}
                for name, (path, digest) in bindings.items()
            ],
        },
        "summary": summary,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    result = build_package(config)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "candidate_contract_drafts.json": result["contract_drafts"],
        "candidate_contract_similarity.json": result["similarity"],
        "candidate_equivalence_test_plan.json": result["equivalence_plan"],
        "dependency_environment_snapshot.json": result["environment"],
        "source_binding_report.json": result["bindings"],
        "contract_package_summary.json": result["summary"],
        "candidate_contract_package_config_snapshot.json": config,
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    manifest = {
        "package_id": config["package_id"],
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
    summary = build_outputs(Path(args.output_dir).resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
