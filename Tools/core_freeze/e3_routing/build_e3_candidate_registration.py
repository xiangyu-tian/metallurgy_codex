"""Build and execute the first nonformal E3 candidate registration package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing import audit_e3_neighbor_feasibility as neighbor_audit
from Tools.core_freeze.e3_routing import candidate_runtime_adapters
from Tools.core_freeze.e3_routing import run_e3_candidate_equivalence as equivalence_runner


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("candidate_registration_config_v1.json")
ID_PATTERN = re.compile(r"^E3C\d{3}$")


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


def binding_path(config: dict[str, Any], suffix: str) -> Path:
    binding = next(row for row in config["bindings"] if row["path"].endswith(suffix))
    path = WORKSPACE / binding["path"]
    validate_bound_file(path, binding["sha256"])
    return path


def validate_holdout_manifest(path: Path) -> dict[str, Any]:
    manifest = load_json(path)
    if manifest["artifact_count"] != len(manifest["artifacts"]):
        raise ValueError("holdout manifest count mismatch")
    filenames = [row["filename"] for row in manifest["artifacts"]]
    if len(filenames) != len(set(filenames)):
        raise ValueError("duplicate holdout artifact filename")
    for artifact in manifest["artifacts"]:
        artifact_path = path.parent / artifact["filename"]
        validate_bound_file(artifact_path, artifact["sha256"])
        if artifact_path.stat().st_size != artifact["bytes"]:
            raise ValueError(f"holdout artifact byte mismatch: {artifact['filename']}")
    return manifest


def validate_parameters(parameters: dict[str, Any]) -> None:
    if parameters.get("type") != "object":
        raise ValueError("candidate parameters must be an object schema")
    properties = parameters.get("properties")
    required = parameters.get("required")
    if not isinstance(properties, dict) or not properties:
        raise ValueError("candidate parameters require properties")
    if not isinstance(required, list) or not required:
        raise ValueError("candidate parameters require required fields")
    if not set(required).issubset(properties):
        raise ValueError("required fields must be declared properties")
    if parameters.get("additionalProperties") is not False:
        raise ValueError("top-level candidate schemas must reject additional properties")


def load_relation_evidence(holdout_dir: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    acceptable = load_json(holdout_dir / "acceptable_equivalence_holdout_results.json")
    mismatches = load_json(holdout_dir / "contract_mismatch_holdout_results.json")
    acceptable_by_id = {row["case_id"]: row for row in acceptable["rows"]}
    mismatch_by_id = {row["case_id"]: row for row in mismatches["rows"]}
    return acceptable_by_id, mismatch_by_id


def build_package(config: dict[str, Any]) -> dict[str, Any]:
    if config.get("local_execution_authorized") is not True:
        raise ValueError("local candidate registration execution is not authorized")
    for key in (
        "external_api_calls_authorized",
        "formal_catalog_mutation_allowed",
        "formal_pool_generation_allowed",
        "confirmatory_inference_allowed",
    ):
        if config.get(key) is not False:
            raise ValueError(f"{key} must remain false")
    for binding in config["bindings"]:
        validate_bound_file(WORKSPACE / binding["path"], binding["sha256"])

    catalog = load_json(binding_path(config, "e3_schema_catalog_v1_candidate.json"))
    verified_contracts = load_json(binding_path(config, "contracts_v1.json"))
    neighbor_config = load_json(binding_path(config, "neighbor_audit_config_v1_1.json"))
    holdout_manifest_path = binding_path(config, "artifact_manifest.json")
    validate_holdout_manifest(holdout_manifest_path)
    acceptable_evidence, mismatch_evidence = load_relation_evidence(holdout_manifest_path.parent)

    lock_binding = next(
        row for row in config["bindings"] if row["path"].endswith("candidate_validation_requirements_lock.txt")
    )
    environment = equivalence_runner.verify_environment(
        {
            "run_id": config["package_id"],
            "requirements_lock_path": lock_binding["path"],
            "requirements_lock_sha256": lock_binding["sha256"],
            "expected_python_version": config["expected_python_version"],
            "expected_top_level_versions": config["expected_top_level_versions"],
        }
    )
    if not environment["environment_verification_passed"]:
        raise RuntimeError("candidate environment does not match frozen lock")

    formal_ids = {row["tool_id"] for row in catalog["entries"]}
    target_entries = {row["tool_id"]: row for row in catalog["entries"]}
    target_contracts = {row["tool_id"]: row for row in verified_contracts["contracts"]}
    candidate_ids = [row["candidate_tool_id"] for row in config["candidates"]]
    provisional_ids = [row["provisional_candidate_id"] for row in config["candidates"]]
    aliases = [row["semantic_alias"] for row in config["candidates"]]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("candidate tool IDs must be unique")
    if len(provisional_ids) != len(set(provisional_ids)):
        raise ValueError("provisional candidate IDs must be unique")
    if len(aliases) != len(set(aliases)):
        raise ValueError("candidate semantic aliases must be unique")
    if any(not ID_PATTERN.fullmatch(value) for value in candidate_ids):
        raise ValueError("candidate tool ID is outside the E3C namespace")
    collisions = sorted(set(candidate_ids) & formal_ids)
    if collisions:
        raise ValueError(f"candidate IDs collide with formal catalog: {collisions}")
    if set(candidate_ids) != set(candidate_runtime_adapters.ADAPTERS):
        raise ValueError("candidate registry and runtime adapter IDs must match exactly")

    runtime_rows = []
    registry_rows = []
    similarity_rows = []
    relation_candidate_counts: dict[str, int] = {
        "acceptable_equivalent": 0,
        "lexical": 0,
        "contract_mismatch": 0,
        "evidence_insufficient": 0,
    }
    for candidate in config["candidates"]:
        candidate_id = candidate["candidate_tool_id"]
        target_id = candidate["target_tool_id"]
        if target_id not in target_entries or target_id not in target_contracts:
            raise ValueError(f"unknown verified target: {target_id}")
        validate_parameters(candidate["parameters"])
        if candidate["package_version"] != config["expected_top_level_versions"][candidate["package"]]:
            raise ValueError(f"package version mismatch in candidate contract: {candidate_id}")

        smoke_rows = []
        for smoke in candidate["smoke_cases"]:
            result = candidate_runtime_adapters.invoke(candidate_id, smoke["input"])
            passed = result["success"] is smoke["expected_success"]
            smoke_row = {
                "candidate_tool_id": candidate_id,
                "case_id": smoke["case_id"],
                "input": smoke["input"],
                "expected_success": smoke["expected_success"],
                "execution": result,
                "contract_outcome_pass": passed,
            }
            smoke_rows.append(smoke_row)
            runtime_rows.append(smoke_row)
        runtime_passed = all(row["contract_outcome_pass"] for row in smoke_rows)

        score_candidate = {
            "tool_id": candidate_id,
            "tool_name": candidate["tool_name"],
            "scenario": candidate["scenario"],
            "core_method": candidate["core_method"],
            "main_input": candidate["main_input"],
            "main_output": candidate["main_output"],
            "lifecycle_status": "candidate_registered_nonformal",
        }
        candidate_contract = {
            "supported_systems": candidate["supported_systems"],
            "data_or_model_version": candidate["data_or_model_version"],
            "service_status": candidate["service_status"],
        }
        similarity = neighbor_audit.score_pair(
            target_entries[target_id],
            score_candidate,
            target_contracts[target_id],
            candidate_contract,
            neighbor_config,
        )
        evidence_ids = candidate["relation_evidence_case_ids"]
        if candidate["relation_policy"] == "acceptable_equivalent":
            evidence_passed = all(
                case_id in acceptable_evidence and acceptable_evidence[case_id]["comparison_pass"]
                for case_id in evidence_ids
            )
            relation = "acceptable_equivalent" if evidence_passed else "evidence_insufficient"
        else:
            evidence_passed = all(
                case_id in mismatch_evidence and mismatch_evidence[case_id]["relation_fixture_pass"]
                for case_id in evidence_ids
            )
            if evidence_passed and similarity["provable_contract_mismatch_neighbor"]:
                relation = "contract_mismatch"
            elif evidence_passed and similarity["algorithmic_lexical_candidate"]:
                relation = "lexical"
            else:
                relation = "evidence_insufficient"
        relation_candidate_counts[relation] += 1
        similarity_rows.append(
            {
                **similarity,
                "relation_policy": candidate["relation_policy"],
                "relation_evidence_case_ids": evidence_ids,
                "relation_evidence_passed": evidence_passed,
                "registration_candidate_relation": relation,
                "formal_relation_admission": False,
            }
        )
        registry_rows.append(
            {
                "candidate_tool_id": candidate_id,
                "provisional_candidate_id": candidate["provisional_candidate_id"],
                "target_tool_id": target_id,
                "semantic_alias": candidate["semantic_alias"],
                "tool_name": candidate["tool_name"],
                "scenario": candidate["scenario"],
                "tool_type": candidate["tool_type"],
                "core_method": candidate["core_method"],
                "main_input": candidate["main_input"],
                "main_output": candidate["main_output"],
                "supported_systems": candidate["supported_systems"],
                "data_or_model_version": candidate["data_or_model_version"],
                "service_status": candidate["service_status"],
                "package": candidate["package"],
                "package_version": candidate["package_version"],
                "openai_tool": {
                    "type": "function",
                    "function": {
                        "name": candidate_id,
                        "description": (
                            f"{candidate['tool_name']}；方法：{candidate['core_method']}；"
                            f"输入：{candidate['main_input']}；输出：{candidate['main_output']}"
                        ),
                        "parameters": candidate["parameters"],
                    },
                },
                "runtime_adapter": (
                    "Tools.core_freeze.e3_routing.candidate_runtime_adapters:invoke"
                ),
                "runtime_contract_passed": runtime_passed,
                "registration_candidate_relation": relation,
                "lifecycle_status": "candidate_registered_nonformal",
                "formal_catalog_entry": False,
                "formal_execution_allowed": False,
                "formal_pool_inclusion_allowed": False,
            }
        )

    runtime_pass_count = sum(row["contract_outcome_pass"] for row in runtime_rows)
    all_runtime_passed = runtime_pass_count == len(runtime_rows)
    report = {
        "package_id": config["package_id"],
        "scope": config["scope"],
        "status": "candidate_registration_package_complete_nonformal",
        "environment_verification_passed": True,
        "formal_catalog_size_before": len(formal_ids),
        "candidate_registration_count": len(registry_rows),
        "candidate_id_collision_count": 0,
        "runtime_smoke_case_count": len(runtime_rows),
        "runtime_smoke_pass_count": runtime_pass_count,
        "all_runtime_contracts_passed": all_runtime_passed,
        "relation_candidate_counts": relation_candidate_counts,
        "formal_catalog_size_after": len(formal_ids),
        "formal_catalog_increment_count": 0,
        "formal_acceptable_tools_admission_count": 0,
        "formal_neighbor_admission_count": 0,
        "filled_relation_slot_count": 0,
        "remaining_lexical_gap": 30,
        "remaining_contract_mismatch_gap": 40,
        "external_api_calls": 0,
        "formal_pool_generation_allowed": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    return {
        "environment": environment,
        "registry": {
            "package_id": config["package_id"],
            "candidate_id_namespace": config["candidate_id_namespace"],
            "candidate_count": len(registry_rows),
            "candidates": registry_rows,
        },
        "runtime": {
            "package_id": config["package_id"],
            "case_count": len(runtime_rows),
            "rows": runtime_rows,
        },
        "similarity": {
            "package_id": config["package_id"],
            "row_count": len(similarity_rows),
            "rows": similarity_rows,
        },
        "report": report,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    result = build_package(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "candidate_registration_registry.json": result["registry"],
        "candidate_runtime_contract_results.json": result["runtime"],
        "candidate_relation_similarity.json": result["similarity"],
        "candidate_registration_report.json": result["report"],
        "candidate_environment_verification.json": result["environment"],
        "candidate_registration_config_snapshot.json": config,
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
    return result["report"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    report = build_outputs(Path(args.output_dir).resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
