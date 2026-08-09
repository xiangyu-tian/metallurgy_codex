"""Build the third nonformal E3 package focused on closing A003 neighbor gaps."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing import audit_e3_neighbor_feasibility as neighbor_audit
from Tools.core_freeze.e3_routing import candidate_runtime_adapters
from Tools.core_freeze.e3_routing import run_e3_candidate_equivalence as environment_runner


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("candidate_registration_batch3_config_v1.json")
ID_PATTERN = re.compile(r"^E3C\d{3}$")


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
        raise ValueError("bound manifest artifact count mismatch")
    names = [row["filename"] for row in manifest["artifacts"]]
    if len(names) != len(set(names)):
        raise ValueError("bound manifest contains duplicate filenames")
    for row in manifest["artifacts"]:
        artifact = path.parent / row["filename"]
        validate_bound_file(artifact, row["sha256"])
        if artifact.stat().st_size != row["bytes"]:
            raise ValueError(f"bound artifact byte mismatch: {artifact}")
    return manifest


def binding(config: dict[str, Any], suffix: str) -> dict[str, str]:
    matches = [row for row in config["bindings"] if row["path"].endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one binding ending with {suffix}")
    return matches[0]


def validate_schema(schema: dict[str, Any]) -> None:
    if schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
        raise ValueError("candidate schema must be an object with properties")
    if not isinstance(schema.get("required"), list) or not schema["required"]:
        raise ValueError("candidate schema must declare required fields")
    if not set(schema["required"]).issubset(schema["properties"]):
        raise ValueError("candidate required fields are not declared")
    if schema.get("additionalProperties") is not False:
        raise ValueError("candidate schema must reject additional properties")


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
        raise ValueError("local batch-3 execution is not authorized")
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
        raise RuntimeError("candidate environment does not match the batch-3 frozen lock")

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
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("duplicate candidate IDs")
    if len(aliases) != len(set(aliases)):
        raise ValueError("duplicate semantic aliases")
    if len(callables) != len(set(callables)):
        raise ValueError("same callable cannot be renamed into multiple candidate tools")
    if set(candidate_ids) != set(candidate_runtime_adapters.BATCH3_ADAPTERS):
        raise ValueError("implemented candidates and batch-3 adapters must match exactly")
    if set(candidate_ids) & set(entries):
        raise ValueError("candidate ID collides with the formal catalog")
    if set(aliases) & {row["semantic_alias"] for row in entries.values()}:
        raise ValueError("candidate semantic alias collides with the formal catalog")
    if {row["target_tool_id"] for row in candidates} != {"A003"}:
        raise ValueError("batch 3 is frozen to A003 only")
    relation_policy_counts = Counter(row["relation_policy"] for row in candidates)
    if relation_policy_counts != Counter({"contract_mismatch": 6, "lexical": 2}):
        raise ValueError("batch 3 must contain exactly two lexical and six mismatch candidates")

    if prior_gap["lexical_gap_after"] != config["starting_gap_state"]["lexical_gap"]:
        raise ValueError("batch-2 lexical gap binding mismatch")
    if prior_gap["contract_mismatch_gap_after"] != config["starting_gap_state"]["contract_mismatch_gap"]:
        raise ValueError("batch-2 contract mismatch gap binding mismatch")
    prior_target = next(row for row in prior_gap["rows"] if row["target_tool_id"] == "A003")
    target_state = config["starting_target_state"]
    if prior_target["lexical_count_after"] != target_state["lexical_count"]:
        raise ValueError("A003 lexical starting count mismatch")
    if prior_target["contract_mismatch_count_after"] != target_state["contract_mismatch_count"]:
        raise ValueError("A003 mismatch starting count mismatch")

    runtime_rows: list[dict[str, Any]] = []
    registry_rows: list[dict[str, Any]] = []
    relation_rows: list[dict[str, Any]] = []
    independence_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = candidate["candidate_tool_id"]
        target_id = candidate["target_tool_id"]
        if candidate["package_version"] != config["expected_top_level_versions"][candidate["package"]]:
            raise ValueError(f"candidate package version mismatch: {candidate_id}")
        if not candidate["source_reference"].startswith("https://"):
            raise ValueError(f"candidate source must be an HTTPS primary source: {candidate_id}")
        validate_schema(candidate["parameters"])
        target = entries[target_id]
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
            target,
            score_candidate,
            target_contracts[target_id],
            candidate_contract,
            audit_config,
        )
        relation = candidate["relation_policy"]
        threshold_passed = (
            score["algorithmic_lexical_candidate"]
            if relation == "lexical"
            else score["provable_contract_mismatch_neighbor"]
        )

        candidate_runtime = []
        for smoke in candidate["smoke_cases"]:
            execution = candidate_runtime_adapters.invoke_batch3(candidate_id, smoke["input"])
            passed = execution["success"] is smoke["expected_success"]
            row = {
                "candidate_tool_id": candidate_id,
                "case_id": smoke["case_id"],
                "case_kind": smoke["case_kind"],
                "input": smoke["input"],
                "expected_success": smoke["expected_success"],
                "execution": execution,
                "contract_outcome_pass": passed,
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
                "target_tool_id": target_id,
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
                            f"{candidate['tool_name']}；方法：{core_method}；"
                            f"输入：{candidate['main_input']}；输出：{candidate['main_output']}；"
                            f"边界：{candidate['relation_mechanism']}"
                        ),
                        "parameters": candidate["parameters"],
                    },
                },
                "runtime_adapter": "Tools.core_freeze.e3_routing.candidate_runtime_adapters:invoke_batch3",
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
        raise ValueError(f"batch-3 runtime contract failures: {failed_cases}")
    relation_counts = Counter(row["registration_candidate_relation"] for row in relation_rows)
    if relation_counts != relation_policy_counts:
        raise ValueError("all eight batch-3 candidates must pass their frozen relation threshold")

    lexical_after = config["starting_gap_state"]["lexical_gap"] - relation_counts["lexical"]
    mismatch_after = config["starting_gap_state"]["contract_mismatch_gap"] - relation_counts["contract_mismatch"]
    target_lexical_after = target_state["lexical_count"] + relation_counts["lexical"]
    target_mismatch_after = target_state["contract_mismatch_count"] + relation_counts["contract_mismatch"]
    report = {
        "package_id": config["package_id"],
        "scope": config["scope"],
        "status": "batch3_registration_complete_a003_candidate_ready",
        "environment_verification_passed": True,
        "implemented_candidate_count": len(registry_rows),
        "independent_callable_count": len(set(callables)),
        "runtime_case_count": len(runtime_rows),
        "runtime_pass_count": len(runtime_rows),
        "all_runtime_contracts_passed": True,
        "relation_candidate_counts": dict(sorted(relation_counts.items())),
        "lexical_gap_before": config["starting_gap_state"]["lexical_gap"],
        "lexical_gap_if_admitted": lexical_after,
        "contract_mismatch_gap_before": config["starting_gap_state"]["contract_mismatch_gap"],
        "contract_mismatch_gap_if_admitted": mismatch_after,
        "a003_lexical_count_if_admitted": target_lexical_after,
        "a003_contract_mismatch_count_if_admitted": target_mismatch_after,
        "a003_paired_8_ready_if_admitted": target_lexical_after >= 8 and target_mismatch_after >= 8,
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    print(json.dumps(build_outputs(Path(args.output_dir).resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
