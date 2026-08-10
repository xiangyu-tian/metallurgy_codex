"""Build the fourth nonformal E3 candidate package to bring A004 to paired 4+4."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing import audit_e3_neighbor_feasibility as neighbor_audit
from Tools.core_freeze.e3_routing import candidate_runtime_adapters
from Tools.core_freeze.e3_routing import run_e3_candidate_equivalence as environment_runner
from Tools.core_freeze.e3_routing.build_e3_candidate_registration_batch3 import (
    binding,
    load_json,
    sha256_file,
    validate_bound_file,
    validate_manifest,
    validate_schema,
    write_json,
)


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("candidate_registration_batch4_config_v1.json")
ID_PATTERN = re.compile(r"^E3C\d{3}$")


def verify_environment(config: dict[str, Any]) -> dict[str, Any]:
    lock = binding(config, "candidate_validation_requirements_batch3_lock.txt")
    return environment_runner.verify_environment(
        {
            "run_id": config["package_id"],
            "requirements_lock_path": lock["path"],
            "requirements_lock_sha256": lock["sha256"],
            "expected_python_version": config["expected_python_version"],
            "expected_top_level_versions": config["expected_top_level_versions"],
        }
    )


def build_package(config: dict[str, Any]) -> dict[str, Any]:
    if config.get("local_execution_authorized") is not True:
        raise ValueError("local batch-4 execution is not authorized")
    for key in (
        "external_api_calls_authorized",
        "formal_catalog_mutation_allowed",
        "formal_pool_generation_allowed",
        "confirmatory_inference_allowed",
    ):
        if config.get(key) is not False:
            raise ValueError(f"{key} must remain false")
    for row in config["bindings"]:
        path = WORKSPACE / row["path"]
        if row["path"].endswith("artifact_manifest.json"):
            validate_manifest(path, row["sha256"])
        else:
            validate_bound_file(path, row["sha256"])

    environment = verify_environment(config)
    if not environment["environment_verification_passed"]:
        raise RuntimeError("candidate environment does not match the frozen lock")
    catalog = load_json(WORKSPACE / binding(config, "e3_schema_catalog_v1_candidate.json")["path"])
    contracts = load_json(WORKSPACE / binding(config, "contracts_v1.json")["path"])
    audit_config = load_json(WORKSPACE / binding(config, "neighbor_audit_config_v1_1.json")["path"])
    prior_manifest_path = WORKSPACE / binding(config, "artifact_manifest.json")["path"]
    prior_gap = load_json(prior_manifest_path.parent / "recalculated_gap_matrix.json")

    entries = {row["tool_id"]: row for row in catalog["entries"]}
    target_contracts = {row["tool_id"]: row for row in contracts["contracts"]}
    candidates = config["implemented_candidates"]
    candidate_ids = [row["candidate_tool_id"] for row in candidates]
    aliases = [row["semantic_alias"] for row in candidates]
    callables = [row["callable_identity"] for row in candidates]
    if any(not ID_PATTERN.fullmatch(value) for value in candidate_ids):
        raise ValueError("candidate ID outside E3C namespace")
    if len(candidate_ids) != len(set(candidate_ids)) or len(aliases) != len(set(aliases)):
        raise ValueError("candidate IDs and aliases must be unique")
    if len(callables) != len(set(callables)):
        raise ValueError("same callable cannot be renamed into multiple candidate tools")
    if set(candidate_ids) != set(candidate_runtime_adapters.BATCH4_ADAPTERS):
        raise ValueError("implemented candidates and batch-4 adapters must match exactly")
    if set(candidate_ids) & set(entries):
        raise ValueError("candidate ID collides with the formal catalog")
    if {row["target_tool_id"] for row in candidates} != {"A004"}:
        raise ValueError("batch 4 is frozen to A004 only")
    relation_policy_counts = Counter(row["relation_policy"] for row in candidates)
    if relation_policy_counts != Counter({"lexical": 1, "contract_mismatch": 1}):
        raise ValueError("batch 4 must contain exactly one lexical and one mismatch candidate")
    if prior_gap["lexical_gap_after"] != config["starting_gap_state"]["lexical_gap"]:
        raise ValueError("batch-3 lexical gap binding mismatch")
    if prior_gap["contract_mismatch_gap_after"] != config["starting_gap_state"]["contract_mismatch_gap"]:
        raise ValueError("batch-3 contract mismatch gap binding mismatch")
    prior_target = next(row for row in prior_gap["rows"] if row["target_tool_id"] == "A004")
    target_state = config["starting_target_state"]
    if (
        prior_target["lexical_count_after"] != target_state["lexical_count"]
        or prior_target["contract_mismatch_count_after"] != target_state["contract_mismatch_count"]
    ):
        raise ValueError("A004 starting relation counts changed")

    runtime_rows: list[dict[str, Any]] = []
    registry_rows: list[dict[str, Any]] = []
    relation_rows: list[dict[str, Any]] = []
    independence_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = candidate["candidate_tool_id"]
        if candidate["package_version"] != config["expected_top_level_versions"][candidate["package"]]:
            raise ValueError(f"candidate package version mismatch: {candidate_id}")
        if not candidate["source_reference"].startswith("https://"):
            raise ValueError(f"candidate source must be HTTPS: {candidate_id}")
        validate_schema(candidate["parameters"])
        target = entries["A004"]
        core_method = (
            target["core_method"]
            if candidate["core_method_mode"] == "target_overlap"
            else f"{candidate['tool_name']}专用算法"
        )
        score_candidate = {
            "tool_id": candidate_id,
            "tool_name": candidate["tool_name"],
            "scenario": target["scenario"],
            "core_method": core_method,
            "main_input": candidate["main_input"],
            "main_output": candidate["main_output"],
            "lifecycle_status": "candidate_registered_nonformal",
        }
        candidate_contract = {
            "supported_systems": candidate["supported_systems"],
            "data_or_model_version": candidate["data_or_model_version"],
            "service_status": candidate["service_status"],
        }
        score = neighbor_audit.score_pair(
            target, score_candidate, target_contracts["A004"], candidate_contract, audit_config
        )
        relation = candidate["relation_policy"]
        threshold_passed = (
            score["algorithmic_lexical_candidate"]
            if relation == "lexical"
            else score["provable_contract_mismatch_neighbor"]
        )
        candidate_runtime = []
        for smoke in candidate["smoke_cases"]:
            execution = candidate_runtime_adapters.invoke_batch4(candidate_id, smoke["input"])
            row = {
                "candidate_tool_id": candidate_id,
                "case_id": smoke["case_id"],
                "case_kind": smoke["case_kind"],
                "input": smoke["input"],
                "expected_success": smoke["expected_success"],
                "execution": execution,
                "contract_outcome_pass": execution["success"] is smoke["expected_success"],
            }
            candidate_runtime.append(row)
            runtime_rows.append(row)
        runtime_passed = all(row["contract_outcome_pass"] for row in candidate_runtime)
        relation_evidence_passed = runtime_passed and bool(candidate["relation_mechanism"]) and threshold_passed
        relation_rows.append(
            {
                **score,
                "relation_policy": relation,
                "relation_mechanism": candidate["relation_mechanism"],
                "runtime_evidence_case_ids": [row["case_id"] for row in candidate_runtime],
                "relation_evidence_passed": relation_evidence_passed,
                "registration_candidate_relation": relation if relation_evidence_passed else "evidence_insufficient",
                "formal_relation_admission": False,
            }
        )
        registry_rows.append(
            {
                "candidate_tool_id": candidate_id,
                "provisional_candidate_id": candidate["provisional_candidate_id"],
                "target_tool_id": "A004",
                "semantic_alias": candidate["semantic_alias"],
                "callable_identity": candidate["callable_identity"],
                "source_reference": candidate["source_reference"],
                **score_candidate,
                **candidate_contract,
                "package": candidate["package"],
                "package_version": candidate["package_version"],
                "openai_tool": {
                    "type": "function",
                    "function": {
                        "name": candidate_id,
                        "description": (
                            f"{candidate['tool_name']}；方法：{core_method}；输入：{candidate['main_input']}；"
                            f"输出：{candidate['main_output']}；边界：{candidate['relation_mechanism']}"
                        ),
                        "parameters": candidate["parameters"],
                    },
                },
                "runtime_adapter": "Tools.core_freeze.e3_routing.candidate_runtime_adapters:invoke_batch4",
                "runtime_contract_passed": runtime_passed,
                "registration_candidate_relation": relation if relation_evidence_passed else "evidence_insufficient",
                "formal_catalog_entry": False,
                "formal_execution_allowed": False,
                "formal_pool_inclusion_allowed": False,
            }
        )
        independence_rows.append(
            {
                "candidate_tool_id": candidate_id,
                "package": candidate["package"],
                "callable_identity": candidate["callable_identity"],
                "semantic_alias": candidate["semantic_alias"],
                "same_callable_renaming": False,
                "distinct_input_or_output_contract": True,
                "source_reference": candidate["source_reference"],
            }
        )
    failed_cases = [row["case_id"] for row in runtime_rows if not row["contract_outcome_pass"]]
    if failed_cases:
        raise ValueError(f"batch-4 runtime contract failures: {failed_cases}")
    relation_counts = Counter(row["registration_candidate_relation"] for row in relation_rows)
    if relation_counts != relation_policy_counts:
        raise ValueError("both batch-4 candidates must pass their frozen relation threshold")
    target_lexical_after = target_state["lexical_count"] + relation_counts["lexical"]
    target_mismatch_after = target_state["contract_mismatch_count"] + relation_counts["contract_mismatch"]
    report = {
        "package_id": config["package_id"],
        "scope": config["scope"],
        "status": "batch4_registration_complete_a004_paired4_candidate_ready",
        "environment_verification_passed": True,
        "implemented_candidate_count": len(registry_rows),
        "independent_callable_count": len(set(callables)),
        "runtime_case_count": len(runtime_rows),
        "runtime_pass_count": len(runtime_rows),
        "all_runtime_contracts_passed": True,
        "relation_candidate_counts": dict(sorted(relation_counts.items())),
        "lexical_gap_before": config["starting_gap_state"]["lexical_gap"],
        "lexical_gap_if_admitted": config["starting_gap_state"]["lexical_gap"] - 1,
        "contract_mismatch_gap_before": config["starting_gap_state"]["contract_mismatch_gap"],
        "contract_mismatch_gap_if_admitted": config["starting_gap_state"]["contract_mismatch_gap"] - 1,
        "a004_lexical_count_if_admitted": target_lexical_after,
        "a004_contract_mismatch_count_if_admitted": target_mismatch_after,
        "a004_paired_4_ready_if_admitted": target_lexical_after >= 4 and target_mismatch_after >= 4,
        "a004_paired_8_ready_if_admitted": target_lexical_after >= 8 and target_mismatch_after >= 8,
        "formal_catalog_size": len(entries),
        "formal_catalog_increment_count": 0,
        "formal_relation_admission_count": 0,
        "external_api_calls": 0,
        "formal_pool_generation_allowed": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    return {
        "environment": environment,
        "registry": {"package_id": config["package_id"], "candidate_count": len(registry_rows), "candidates": registry_rows},
        "runtime": {"package_id": config["package_id"], "case_count": len(runtime_rows), "rows": runtime_rows},
        "relations": {"package_id": config["package_id"], "row_count": len(relation_rows), "rows": relation_rows},
        "independence": {"package_id": config["package_id"], "row_count": len(independence_rows), "rows": independence_rows},
        "report": report,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    result = build_package(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "candidate_registration_registry.json": result["registry"],
        "candidate_runtime_contract_results.json": result["runtime"],
        "candidate_relation_evidence.json": result["relations"],
        "candidate_independence_matrix.json": result["independence"],
        "candidate_environment_verification.json": result["environment"],
        "candidate_registration_report.json": result["report"],
        "candidate_registration_config_snapshot.json": config,
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    manifest = {
        "package_id": config["package_id"],
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
