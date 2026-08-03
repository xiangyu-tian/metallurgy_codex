"""Execute the frozen E3 equivalence plan in the isolated candidate environment."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
from collections import Counter
from pathlib import Path
from typing import Any

from packaging.utils import canonicalize_name


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("candidate_equivalence_execution_config_v1.json")


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


def parse_lock(path: Path) -> dict[str, str]:
    locked = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            raise ValueError(f"unfrozen requirement: {line}")
        name, version = line.split("==", 1)
        key = canonicalize_name(name)
        if key in locked:
            raise ValueError(f"duplicate locked distribution: {name}")
        locked[key] = version
    return locked


def verify_environment(config: dict[str, Any]) -> dict[str, Any]:
    lock_path = WORKSPACE / config["requirements_lock_path"]
    validate_bound_file(lock_path, config["requirements_lock_sha256"])
    locked = parse_lock(lock_path)
    installed = {
        canonicalize_name(dist.metadata["Name"]): dist.version
        for dist in importlib.metadata.distributions()
        if dist.metadata.get("Name")
    }
    missing = sorted(set(locked) - set(installed))
    unexpected = sorted(set(installed) - set(locked))
    mismatched = [
        {"distribution": name, "locked": version, "installed": installed.get(name)}
        for name, version in sorted(locked.items())
        if name in installed and installed[name] != version
    ]
    python_version = platform.python_version()
    top_level = {
        name: importlib.metadata.version(name)
        for name in config["expected_top_level_versions"]
    }
    top_level_matches = all(
        top_level[name] == version
        for name, version in config["expected_top_level_versions"].items()
    )
    passed = (
        python_version == config["expected_python_version"]
        and not missing
        and not unexpected
        and not mismatched
        and top_level_matches
    )
    return {
        "run_id": config["run_id"],
        "python_version": python_version,
        "expected_python_version": config["expected_python_version"],
        "locked_distribution_count": len(locked),
        "installed_distribution_count": len(installed),
        "missing_distributions": missing,
        "unexpected_distributions": unexpected,
        "version_mismatches": mismatched,
        "top_level_versions": top_level,
        "top_level_versions_match": top_level_matches,
        "requirements_lock_sha256": config["requirements_lock_sha256"],
        "environment_verification_passed": passed,
    }


def _expected_success(case: dict[str, Any]) -> bool:
    return bool(case["expected"]["success"])


def _expected_check(case: dict[str, Any], path: str) -> dict[str, Any] | None:
    for check in case["expected"].get("checks", []):
        if check["path"] == path:
            return check
    return None


def _compare_number(actual: float, check: dict[str, Any]) -> bool:
    if check["op"] == "approx":
        return abs(float(actual) - float(check["value"])) <= float(check["abs_tol"])
    if check["op"] == "equal":
        return float(actual) == float(check["value"])
    raise ValueError(f"unsupported numeric comparison: {check['op']}")


def _compare_mapping(actual: dict[str, Any], check: dict[str, Any]) -> bool:
    expected = check["value"]
    if set(actual) != set(expected):
        return False
    return all(abs(float(actual[key]) - float(expected[key])) <= 1e-12 for key in expected)


def _run_candidate(
    candidate_id: str,
    case: dict[str, Any],
    config: dict[str, Any],
) -> tuple[bool | None, dict[str, Any] | None, str | None, str | None, bool]:
    try:
        if candidate_id == "SRC-PINT-001":
            import pint

            source = config["unit_aliases"].get(case["input"]["source_unit"], case["input"]["source_unit"])
            target = config["unit_aliases"].get(case["input"]["target_unit"], case["input"]["target_unit"])
            registry = pint.UnitRegistry()
            quantity = registry.Quantity(case["input"]["value"], source)
            converted = quantity.to(target)
            return True, {"converted_value": float(converted.magnitude)}, None, None, True

        if candidate_id == "SRC-PMG-001":
            from pymatgen.core import Composition

            composition = Composition(case["input"]["formula"])
            return True, {"amounts": composition.get_el_amt_dict()}, None, None, True

        if candidate_id == "SRC-RDKIT-004":
            from rdkit import Chem
            from rdkit.Chem import Descriptors

            formula = case["input"]["formula"]
            smiles = config["formula_to_smiles_probe_mapping"].get(formula)
            if smiles is None:
                return None, None, "ADAPTER_UNAVAILABLE", "no frozen formula-to-SMILES mapping", False
            molecule = Chem.MolFromSmiles(smiles)
            if molecule is None:
                raise ValueError("RDKit rejected the frozen probe SMILES")
            return True, {"average_molecular_weight": float(Descriptors.MolWt(molecule))}, None, None, True

        if candidate_id == "SRC-PMG-002":
            from pymatgen.core import Composition

            composition = Composition(case["input"]["formula"])
            return True, {"composition_weight": float(composition.weight)}, None, None, True

        if candidate_id == "SRC-PMG-003":
            from pymatgen.core import Composition

            composition = Composition(case["input"]["compositions"])
            values = composition.fractional_composition.get_el_amt_dict()
            return True, {"fractional_amounts": values}, None, None, True

        raise ValueError(f"unsupported candidate: {candidate_id}")
    except Exception as exc:  # candidate failure is part of the frozen boundary test
        return False, None, type(exc).__name__, str(exc)[:300], True


def _compare_case(
    candidate_id: str,
    case: dict[str, Any],
    candidate_success: bool | None,
    output: dict[str, Any] | None,
    adapter_available: bool,
) -> tuple[bool, str]:
    if not adapter_available:
        return False, "adapter_unavailable"
    expected_success = _expected_success(case)
    if candidate_success != expected_success:
        return False, "success_failure_outcome_mismatch"
    if not expected_success:
        return True, "both_rejected_input"
    if output is None:
        return False, "missing_candidate_output"
    if candidate_id == "SRC-PINT-001":
        check = _expected_check(case, "value")
        return _compare_number(output["converted_value"], check), "numeric_value_comparison"
    if candidate_id == "SRC-PMG-001":
        check = _expected_check(case, "elements")
        return _compare_mapping(output["amounts"], check), "element_amount_mapping_comparison"
    if candidate_id == "SRC-RDKIT-004":
        check = _expected_check(case, "molar_mass")
        return _compare_number(output["average_molecular_weight"], check), "average_weight_comparison"
    if candidate_id == "SRC-PMG-002":
        check = _expected_check(case, "molar_mass")
        return _compare_number(output["composition_weight"], check), "composition_weight_comparison"
    if candidate_id == "SRC-PMG-003":
        check = _expected_check(case, "normalized")
        return _compare_mapping(output["fractional_amounts"], check), "fractional_mapping_comparison"
    raise ValueError(candidate_id)


def execute(config: dict[str, Any]) -> dict[str, Any]:
    if config.get("local_candidate_execution_authorized") is not True:
        raise ValueError("local candidate execution is not authorized")
    if config.get("external_api_calls_authorized") is not False:
        raise ValueError("equivalence execution must remain offline")
    if config.get("confirmatory_inference_allowed") is not False:
        raise ValueError("candidate equivalence run must remain nonconfirmatory")
    plan_path = WORKSPACE / config["equivalence_plan_path"]
    reference_path = WORKSPACE / config["reference_cases_path"]
    validate_bound_file(plan_path, config["equivalence_plan_sha256"])
    validate_bound_file(reference_path, config["reference_cases_sha256"])
    environment = verify_environment(config)
    if not environment["environment_verification_passed"]:
        raise RuntimeError("candidate environment does not match the frozen lock")

    plan = load_json(plan_path)
    reference_cases = load_json(reference_path)
    reference_by_id = {row["case_id"]: row for row in reference_cases["cases"]}
    case_rows = []
    candidate_summaries = []
    for test in plan["tests"]:
        candidate_id = test["provisional_candidate_id"]
        overlap_ids = set(test["overlap_reference_case_ids"])
        all_ids = [*test["overlap_reference_case_ids"], *test["boundary_reference_case_ids"]]
        candidate_rows = []
        for case_id in all_ids:
            case = reference_by_id[case_id]
            success, output, error_type, error_message, adapter_available = _run_candidate(
                candidate_id, case, config
            )
            comparison_pass, comparison_basis = _compare_case(
                candidate_id,
                case,
                success,
                output,
                adapter_available,
            )
            row = {
                "provisional_candidate_id": candidate_id,
                "target_tool_id": test["target_tool_id"],
                "reference_case_id": case_id,
                "case_partition": "overlap" if case_id in overlap_ids else "boundary",
                "expected_success": _expected_success(case),
                "adapter_available": adapter_available,
                "candidate_success": success,
                "candidate_output": output,
                "candidate_error_type": error_type,
                "candidate_error_message": error_message,
                "comparison_pass": comparison_pass,
                "comparison_basis": comparison_basis,
            }
            candidate_rows.append(row)
            case_rows.append(row)
        pass_count = sum(row["comparison_pass"] for row in candidate_rows)
        overlap_rows = [row for row in candidate_rows if row["case_partition"] == "overlap"]
        all_pass = pass_count == len(candidate_rows)
        all_overlap_pass = all(row["comparison_pass"] for row in overlap_rows)
        adapter_generalizable = bool(test["adapter_generalizable_over_target_scope"])
        if all_pass and adapter_generalizable:
            classification = "exact_equivalent_over_frozen_scope"
        elif all_overlap_pass and not adapter_generalizable:
            classification = "partial_equivalent_overlap_only"
        else:
            classification = "not_equivalent_over_frozen_scope"
        candidate_summaries.append(
            {
                "provisional_candidate_id": candidate_id,
                "target_tool_id": test["target_tool_id"],
                "case_count": len(candidate_rows),
                "comparison_pass_count": pass_count,
                "comparison_fail_count": len(candidate_rows) - pass_count,
                "adapter_generalizable_over_target_scope": adapter_generalizable,
                "equivalence_classification": classification,
                "may_enter_acceptable_tool_set": classification == "exact_equivalent_over_frozen_scope",
                "conditional_acceptable_subdomain_only": classification == "partial_equivalent_overlap_only",
                "may_enter_unacceptable_neighbor_set": False,
                "neighbor_fixture_still_required": classification != "exact_equivalent_over_frozen_scope",
            }
        )

    classifications = Counter(row["equivalence_classification"] for row in candidate_summaries)
    report = {
        "run_id": config["run_id"],
        "scope": config["scope"],
        "status": "completed_nonconfirmatory_equivalence_evidence",
        "environment_verification_passed": True,
        "candidate_count": len(candidate_summaries),
        "case_count": len(case_rows),
        "comparison_pass_count": sum(row["comparison_pass"] for row in case_rows),
        "comparison_fail_count": sum(not row["comparison_pass"] for row in case_rows),
        "classification_counts": dict(sorted(classifications.items())),
        "acceptable_tool_candidate_count": sum(row["may_enter_acceptable_tool_set"] for row in candidate_summaries),
        "conditional_subdomain_candidate_count": sum(row["conditional_acceptable_subdomain_only"] for row in candidate_summaries),
        "unacceptable_neighbor_admission_count": 0,
        "catalog_increment_count": 0,
        "filled_relation_slot_count": 0,
        "remaining_lexical_gap": 30,
        "remaining_contract_mismatch_gap": 40,
        "external_api_calls": 0,
        "confirmatory_inference_allowed": False,
        "formal_pool_generation_allowed": False,
        "core_frozen": False,
    }
    return {
        "environment": environment,
        "case_results": {
            "run_id": config["run_id"],
            "case_count": len(case_rows),
            "rows": case_rows,
        },
        "candidate_summary": {
            "run_id": config["run_id"],
            "candidate_count": len(candidate_summaries),
            "candidates": candidate_summaries,
        },
        "report": report,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    result = execute(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "environment_lock_verification.json": result["environment"],
        "equivalence_case_results.json": result["case_results"],
        "equivalence_candidate_summary.json": result["candidate_summary"],
        "equivalence_run_report.json": result["report"],
        "equivalence_execution_config_snapshot.json": config,
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
