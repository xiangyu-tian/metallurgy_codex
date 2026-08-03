"""Run post-equivalence input holdouts for E3 candidate relations."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing import pint_unit_adapter
from Tools.core_freeze.e3_routing import run_e3_candidate_equivalence as equivalence_runner


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("candidate_holdout_config_v1.json")
TOOLS_ROOT = WORKSPACE / "Tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))


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


def canonical_input(target_tool_id: str, value: dict[str, Any]) -> str:
    return f"{target_tool_id}:" + json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def verify_novel_inputs(config: dict[str, Any], reference_cases: dict[str, Any]) -> dict[str, Any]:
    frozen = {
        canonical_input(row["tool_id"], row["input"])
        for row in reference_cases["cases"]
    }
    proposed_rows = [
        *config["acceptable_equivalence_cases"],
        *config["contract_mismatch_cases"],
    ]
    proposed = [canonical_input(row["target_tool_id"], row["input"]) for row in proposed_rows]
    duplicates = sorted(set(proposed) & frozen)
    repeated_proposed = sorted({value for value in proposed if proposed.count(value) > 1})
    return {
        "frozen_reference_case_count": len(reference_cases["cases"]),
        "proposed_case_count": len(proposed_rows),
        "exact_input_duplicates_with_frozen_references": duplicates,
        "duplicate_inputs_within_holdout": repeated_proposed,
        "input_novelty_passed": not duplicates and not repeated_proposed,
    }


def invoke_target(tool_id: str, params: dict[str, Any]) -> dict[str, Any]:
    from models_core.models_a import (
        A001_UnitConversion,
        A002_ChemicalFormulaParser,
        A003_MolarMassCalculator,
        A004_CompositionNormalizer,
    )

    tools = {
        "A001": A001_UnitConversion,
        "A002": A002_ChemicalFormulaParser,
        "A003": A003_MolarMassCalculator,
        "A004": A004_CompositionNormalizer,
    }
    result = tools[tool_id]().invoke(params)
    return {
        "success": bool(result.success),
        "result": result.result if result.success else None,
        "error_code": result.error_code,
        "error": result.error,
    }


def invoke_candidate(candidate_id: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        if candidate_id == "SRC-PINT-001":
            return pint_unit_adapter.invoke(params)
        if candidate_id == "SRC-PMG-001":
            from pymatgen.core import Composition

            composition = Composition(params["formula"])
            return {
                "success": True,
                "result": {"elements": composition.get_el_amt_dict()},
                "error_code": None,
                "error": None,
            }
        if candidate_id == "SRC-RDKIT-004":
            return {
                "success": None,
                "result": None,
                "error_code": "ADAPTER_UNAVAILABLE",
                "error": "raw formula cannot be generally converted to an RDKit molecular object",
            }
        if candidate_id == "SRC-PMG-002":
            from pymatgen.core import Composition

            composition = Composition(params["formula"])
            return {
                "success": True,
                "result": {"molar_mass": float(composition.weight)},
                "error_code": None,
                "error": None,
            }
        if candidate_id == "SRC-PMG-003":
            from pymatgen.core import Composition

            composition = Composition(params["compositions"])
            return {
                "success": True,
                "result": {"normalized": composition.fractional_composition.get_el_amt_dict()},
                "error_code": None,
                "error": None,
            }
        raise ValueError(f"unsupported candidate: {candidate_id}")
    except Exception as exc:
        return {
            "success": False,
            "result": None,
            "error_code": type(exc).__name__,
            "error": str(exc)[:300],
        }


def acceptable_comparison(target: dict[str, Any], candidate: dict[str, Any], tolerance: float) -> tuple[bool, str]:
    if not target["success"] or not candidate["success"]:
        return False, "success_outcome_mismatch"
    target_value = float(target["result"]["value"])
    candidate_value = float(candidate["result"]["value"])
    return abs(target_value - candidate_value) <= tolerance, "converted_value_comparison"


def mismatch_comparison(
    candidate_id: str,
    target: dict[str, Any],
    candidate: dict[str, Any],
    tolerance: float,
) -> tuple[bool, str]:
    if candidate_id in {"SRC-PMG-001", "SRC-PMG-003"}:
        return (
            target["success"] is False and candidate["success"] is True,
            "target_rejects_candidate_accepts_invalid_boundary",
        )
    if candidate_id == "SRC-RDKIT-004":
        return (
            target["success"] is True and candidate["error_code"] == "ADAPTER_UNAVAILABLE",
            "target_executes_candidate_input_adapter_unavailable",
        )
    if candidate_id == "SRC-PMG-002":
        if not target["success"] or not candidate["success"]:
            return False, "unexpected_execution_failure"
        difference = abs(
            float(target["result"]["molar_mass"])
            - float(candidate["result"]["molar_mass"])
        )
        return difference > tolerance, "numeric_result_exceeds_frozen_tolerance"
    raise ValueError(candidate_id)


def execute(config: dict[str, Any]) -> dict[str, Any]:
    if config.get("local_execution_authorized") is not True:
        raise ValueError("local holdout execution is not authorized")
    for key in (
        "external_api_calls_authorized",
        "formal_registration_allowed",
        "formal_pool_generation_allowed",
        "confirmatory_inference_allowed",
    ):
        if config.get(key) is not False:
            raise ValueError(f"{key} must remain false")
    for binding in config["bindings"]:
        validate_bound_file(WORKSPACE / binding["path"], binding["sha256"])
    contract_path = WORKSPACE / config["pint_contract_path"]
    validate_bound_file(contract_path, config["pint_contract_sha256"])
    contract = load_json(contract_path)

    lock_binding = next(
        row for row in config["bindings"] if row["path"].endswith("candidate_validation_requirements_lock.txt")
    )
    environment_config = {
        "run_id": config["run_id"],
        "requirements_lock_path": lock_binding["path"],
        "requirements_lock_sha256": lock_binding["sha256"],
        "expected_python_version": config["expected_python_version"],
        "expected_top_level_versions": config["expected_top_level_versions"],
    }
    environment = equivalence_runner.verify_environment(environment_config)
    if not environment["environment_verification_passed"]:
        raise RuntimeError("candidate environment does not match frozen lock")

    reference_path = next(
        WORKSPACE / row["path"]
        for row in config["bindings"]
        if row["path"].endswith("reference_cases_v1.json")
    )
    novelty = verify_novel_inputs(config, load_json(reference_path))
    if not novelty["input_novelty_passed"]:
        raise ValueError("holdout inputs duplicate frozen reference content")

    tolerance = float(config["numeric_abs_tolerance"])
    acceptable_rows = []
    for case in config["acceptable_equivalence_cases"]:
        target = invoke_target(case["target_tool_id"], case["input"])
        candidate = invoke_candidate(case["candidate_id"], case["input"])
        passed, basis = acceptable_comparison(target, candidate, tolerance)
        acceptable_rows.append(
            {
                **case,
                "target_execution": target,
                "candidate_execution": candidate,
                "comparison_basis": basis,
                "comparison_pass": passed,
            }
        )

    mismatch_rows = []
    for case in config["contract_mismatch_cases"]:
        target = invoke_target(case["target_tool_id"], case["input"])
        candidate = invoke_candidate(case["candidate_id"], case["input"])
        passed, basis = mismatch_comparison(case["candidate_id"], target, candidate, tolerance)
        mismatch_rows.append(
            {
                **case,
                "target_execution": target,
                "candidate_execution": candidate,
                "comparison_basis": basis,
                "relation_fixture_pass": passed,
                "formal_neighbor_admission": False,
            }
        )

    acceptable_pass_count = sum(row["comparison_pass"] for row in acceptable_rows)
    mismatch_pass_count = sum(row["relation_fixture_pass"] for row in mismatch_rows)
    runtime_verification_passed = acceptable_pass_count == len(acceptable_rows)
    relation_fixture_verification_passed = mismatch_pass_count == len(mismatch_rows)
    report = {
        "run_id": config["run_id"],
        "scope": config["scope"],
        "status": "completed_nonconfirmatory_holdout_evidence",
        "environment_verification_passed": True,
        "input_novelty_passed": True,
        "acceptable_equivalence_case_count": len(acceptable_rows),
        "acceptable_equivalence_pass_count": acceptable_pass_count,
        "pint_runtime_verification_passed": runtime_verification_passed,
        "pint_registration_candidate_ready": runtime_verification_passed,
        "formal_acceptable_tools_admission_count": 0,
        "contract_mismatch_case_count": len(mismatch_rows),
        "contract_mismatch_fixture_pass_count": mismatch_pass_count,
        "relation_fixture_verification_passed": relation_fixture_verification_passed,
        "formal_neighbor_admission_count": 0,
        "catalog_increment_count": 0,
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
        "novelty": novelty,
        "contract_snapshot": contract,
        "acceptable_results": {
            "run_id": config["run_id"],
            "case_count": len(acceptable_rows),
            "rows": acceptable_rows,
        },
        "mismatch_results": {
            "run_id": config["run_id"],
            "case_count": len(mismatch_rows),
            "rows": mismatch_rows,
        },
        "report": report,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    result = execute(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "environment_lock_verification.json": result["environment"],
        "holdout_input_novelty_report.json": result["novelty"],
        "pint_candidate_contract_snapshot.json": result["contract_snapshot"],
        "acceptable_equivalence_holdout_results.json": result["acceptable_results"],
        "contract_mismatch_holdout_results.json": result["mismatch_results"],
        "candidate_holdout_run_report.json": result["report"],
        "candidate_holdout_config_snapshot.json": config,
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    manifest = {
        "run_id": config["run_id"],
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
