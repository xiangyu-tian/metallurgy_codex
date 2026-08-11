"""Build A002/A003 minimal-pair tasks from independent arithmetic references."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common


TOOLS_DIR = Path(__file__).resolve().parents[2]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from models_core import ModelRegistry  # noqa: E402


CONFIG_PATH = Path(__file__).with_name("a002_a003_minimal_pair_taskset_config_v1.json")


def validate_config(config: dict[str, Any]) -> None:
    if config["pair_count"] != 8 or config["task_count"] != 16:
        raise ValueError("taskset must remain eight pairs and sixteen tasks")
    if len(config["formula_specs"]) != config["pair_count"]:
        raise ValueError("formula specification count mismatch")
    if len({row["pair_key"] for row in config["formula_specs"]}) != config["pair_count"]:
        raise ValueError("duplicate pair keys")
    if len({row["formula"] for row in config["formula_specs"]}) != config["pair_count"]:
        raise ValueError("duplicate formulas")
    if config["local_deterministic_tool_execution_allowed"] is not True:
        raise ValueError("local deterministic validation must remain enabled")
    for field in (
        "external_api_calls_allowed",
        "automatic_retry_allowed",
        "full_catalog_acceptable_set_claim_allowed",
        "formal_gold_mutation_allowed",
        "confirmatory_use_allowed",
        "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")


def atomic_weight_text(expansion: dict[str, int], weights: dict[str, float]) -> str:
    return "，".join(f"{element}={weights[element]}" for element in expansion)


def independent_reference(spec: dict[str, Any], weights: dict[str, float]) -> dict[str, Any]:
    expansion = spec["expansion"]
    if not expansion or any(not isinstance(count, int) or count <= 0 for count in expansion.values()):
        raise ValueError(f"invalid manual expansion: {spec['pair_key']}")
    missing = sorted(set(expansion) - set(weights))
    if missing:
        raise ValueError(f"formula exceeds frozen element subset: {spec['pair_key']} {missing}")
    contributions = {
        element: round(weights[element] * count, 12) for element, count in expansion.items()
    }
    molar_mass = round(sum(contributions.values()), 4)
    return {
        "pair_key": spec["pair_key"],
        "formula": spec["formula"],
        "manual_expansion": expansion,
        "atomic_weights": {element: weights[element] for element in expansion},
        "mass_contributions": contributions,
        "molar_mass": molar_mass,
        "unit": "g/mol",
        "reference_method": "manual_expansion_and_arithmetic_not_tool_runtime_output",
        "oracle_independent_of_tool_runtime": True,
    }


def task_rows(reference: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    pair_key = reference["pair_key"]
    formula = reference["formula"]
    weights_text = atomic_weight_text(reference["manual_expansion"], reference["atomic_weights"])
    common_stem = f"给定中性化学式 {formula}，采用冻结原子量（{weights_text}）。"
    common_fields = {
        "pair_id": f"PAIR-A002-A003-{pair_key}",
        "family_id": config["family_id"],
        "contrast_axis": "requested_output_only",
        "canonical_inputs": {"formula": formula},
        "full_catalog_acceptable_set_frozen": False,
        "requires_pool_specific_acceptable_tool_revalidation": True,
        "confirmatory_use_allowed": False,
    }
    parse_task = {
        "task_id": f"E3-MP-{pair_key}-ELEMENTS",
        **common_fields,
        "pair_variant": "element_stoichiometry",
        "target_tool_id": "A002",
        "problem_text": common_stem + "任务：解析该化学式，仅返回各元素的化学计量数。",
        "executable_reference": {
            "elements": reference["manual_expansion"],
            "reference_method": reference["reference_method"],
            "oracle_independent_of_tool_runtime": True,
        },
        "scoring_rule": {
            "type": "structured_path_checks",
            "checks": [{"path": "elements", "op": "equal", "value": reference["manual_expansion"]}],
        },
        "core_pair_primary_acceptable_tools": ["A002"],
        "core_pair_alternative_success_tools": [],
        "expected_family_metrics": {
            "A002": {"primary": True, "family": True, "alternative": False, "scientific": True},
            "A003": {"primary": False, "family": True, "alternative": False, "scientific": False},
        },
    }
    mass_task = {
        "task_id": f"E3-MP-{pair_key}-MOLAR-MASS",
        **common_fields,
        "pair_variant": "molar_mass",
        "target_tool_id": "A003",
        "problem_text": common_stem + "任务：计算该化学式的摩尔质量，返回数值和单位 g/mol，数值保留4位小数。",
        "executable_reference": {
            "molar_mass": reference["molar_mass"],
            "unit": "g/mol",
            "absolute_tolerance": config["molar_mass_abs_tolerance"],
            "reference_method": reference["reference_method"],
            "oracle_independent_of_tool_runtime": True,
        },
        "scoring_rule": {
            "type": "structured_path_checks",
            "checks": [
                {"path": "molar_mass", "op": "approx", "value": reference["molar_mass"],
                 "abs_tol": config["molar_mass_abs_tolerance"], "rel_tol": 0.0},
                {"path": "unit", "op": "equal", "value": "g/mol"},
            ],
        },
        "core_pair_primary_acceptable_tools": ["A003"],
        "core_pair_alternative_success_tools": ["A002"],
        "expected_family_metrics": {
            "A002": {"primary": False, "family": True, "alternative": True, "scientific": True},
            "A003": {"primary": True, "family": True, "alternative": False, "scientific": True},
        },
    }
    return [parse_task, mass_task]


def validate_runtime(reference: dict[str, Any], registry: ModelRegistry,
                     tolerance: float) -> dict[str, Any]:
    params = {"formula": reference["formula"]}
    a002 = registry.invoke("A002", params)
    a003 = registry.invoke("A003", params)
    a002_elements = a002.result.get("elements") if a002.success else None
    a002_mass = a002.result.get("molar_mass") if a002.success else None
    a003_mass = a003.result.get("molar_mass") if a003.success else None
    return {
        "pair_key": reference["pair_key"],
        "formula": reference["formula"],
        "a002_execution_success": a002.success,
        "a003_execution_success": a003.success,
        "a002_elements_match_independent_reference": a002_elements == reference["manual_expansion"],
        "a003_elements_absent": "elements" not in (a003.result or {}),
        "a002_mass_matches_independent_reference": bool(
            isinstance(a002_mass, (int, float))
            and math.isclose(float(a002_mass), reference["molar_mass"], rel_tol=0.0, abs_tol=tolerance)
        ),
        "a003_mass_matches_independent_reference": bool(
            isinstance(a003_mass, (int, float))
            and math.isclose(float(a003_mass), reference["molar_mass"], rel_tol=0.0, abs_tol=tolerance)
        ),
        "a002_explicit_unit_absent": "unit" not in (a002.result or {}),
        "a003_explicit_unit_matches": (a003.result or {}).get("unit") == "g/mol",
        "passed": bool(
            a002.success
            and a003.success
            and a002_elements == reference["manual_expansion"]
            and "elements" not in (a003.result or {})
            and isinstance(a002_mass, (int, float))
            and isinstance(a003_mass, (int, float))
            and math.isclose(float(a002_mass), reference["molar_mass"], rel_tol=0.0, abs_tol=tolerance)
            and math.isclose(float(a003_mass), reference["molar_mass"], rel_tol=0.0, abs_tol=tolerance)
            and "unit" not in (a002.result or {})
            and (a003.result or {}).get("unit") == "g/mol"
        ),
    }


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {name: common.validate_binding(binding) for name, binding in config["bindings"].items()}
    adoption = common.load_json(paths["governance_adoption"])
    contracts_doc = common.load_json(paths["verified_contracts"])
    if adoption["decision"] != "adopted" or adoption["adopted_rules"]["family_id"] != config["family_id"]:
        raise ValueError("adopted governance does not authorize this taskset")
    contracts = {row["tool_id"]: row for row in contracts_doc["contracts"] if row["tool_id"] in ("A002", "A003")}
    weights = contracts["A003"]["verification_scope"]["elements"]

    references = [independent_reference(spec, weights) for spec in config["formula_specs"]]
    tasks = [task for reference in references for task in task_rows(reference, config)]
    if len(tasks) != config["task_count"] or len({row["task_id"] for row in tasks}) != len(tasks):
        raise ValueError("generated task count or uniqueness mismatch")

    registry = ModelRegistry()
    registry.discover()
    validation_rows = [
        validate_runtime(reference, registry, config["molar_mass_abs_tolerance"])
        for reference in references
    ]
    pair_minimality = all(
        tasks[index]["problem_text"].split("任务：", 1)[0]
        == tasks[index + 1]["problem_text"].split("任务：", 1)[0]
        for index in range(0, len(tasks), 2)
    )
    report = {
        "schema_version": "1.0",
        "taskset_id": config["taskset_id"],
        "status": "development_minimal_pair_taskset_candidate_built",
        "governance_record_id": adoption["record_id"],
        "pair_count": len(references),
        "task_count": len(tasks),
        "element_task_count": sum(row["pair_variant"] == "element_stoichiometry" for row in tasks),
        "molar_mass_task_count": sum(row["pair_variant"] == "molar_mass" for row in tasks),
        "identical_pair_stem_count": sum(
            tasks[index]["problem_text"].split("任务：", 1)[0]
            == tasks[index + 1]["problem_text"].split("任务：", 1)[0]
            for index in range(0, len(tasks), 2)
        ),
        "pair_minimality_passed": pair_minimality,
        "independent_reference_count": len(references),
        "runtime_validation_passed_count": sum(row["passed"] for row in validation_rows),
        "local_tool_calls_executed": len(validation_rows) * 2,
        "full_catalog_acceptable_set_frozen": False,
        "requires_pool_specific_acceptable_tool_revalidation": True,
        "formal_gold_mutated": False,
        "external_api_calls": 0,
        "confirmatory_use_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "next_gate": "construct hash-bound 17/120 development routing views and revalidate pool-specific acceptable tools",
    }
    return {
        "adoption": adoption,
        "references": references,
        "tasks": tasks,
        "validation_rows": validation_rows,
        "report": report,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = common.load_json(CONFIG_PATH)
    result = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a002_a003_minimal_pair_config_snapshot.json": config,
        "a002_a003_governance_adoption_snapshot.json": result["adoption"],
        "a002_a003_minimal_pair_taskset_candidate.json": {
            "schema_version": "1.0",
            "taskset_id": config["taskset_id"],
            "status": "candidate_not_formal_gold",
            "tasks": result["tasks"],
        },
        "a002_a003_independent_reference_ledger.json": {
            "schema_version": "1.0", "references": result["references"]
        },
        "a002_a003_local_runtime_validation.json": {
            "schema_version": "1.0", "rows": result["validation_rows"]
        },
        "a002_a003_minimal_pair_taskset_report.json": result["report"],
    }
    for filename, value in artifacts.items():
        common.write_json(output_dir / filename, value)
    artifact_paths = list(output_dir.iterdir())
    common.write_json(output_dir / "artifact_manifest.json", {
        "schema_version": "1.0",
        "taskset_id": config["taskset_id"],
        "artifact_count": len(artifact_paths),
        "artifacts": [
            {"filename": path.name, "sha256": common.file_hash(path), "bytes": path.stat().st_size}
            for path in sorted(artifact_paths, key=lambda item: item.name)
        ],
    })
    return result["report"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else common.WORKSPACE / args.output_dir
    report = build_outputs(output_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["runtime_validation_passed_count"] == report["pair_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
