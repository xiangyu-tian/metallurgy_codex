"""Audit asymmetric A002/A003 functional overlap against frozen A003 tasks."""

from __future__ import annotations

import argparse
import json
import math
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common


TOOLS_DIR = Path(__file__).resolve().parents[2]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from models_core import ModelRegistry  # noqa: E402


CONFIG_PATH = Path(__file__).with_name("a002_a003_overlap_audit_config_v1.json")


def validate_config(config: dict[str, Any]) -> None:
    if (config["source_tool_id"], config["target_tool_id"]) != ("A002", "A003"):
        raise ValueError("audit scope must remain A002 -> A003")
    if config["expected_task_count"] != 12:
        raise ValueError("audit scope must remain twelve frozen A003 tasks")
    for field in (
        "primary_direct_acceptance_requires_explicit_unit",
        "alternative_success_allows_verified_contract_implied_unit",
        "local_deterministic_tool_execution_allowed",
    ):
        if config[field] is not True:
            raise ValueError(f"{field} must remain true")
    for field in (
        "external_api_calls_allowed",
        "automatic_retry_allowed",
        "formal_catalog_mutation_allowed",
        "formal_gold_mutation_allowed",
        "confirmatory_inference_allowed",
        "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")


def primary_check(task: dict[str, Any]) -> dict[str, float]:
    checks = task["scoring_rule"]["checks"]
    if len(checks) != 1 or checks[0].get("path") != "molar_mass" or checks[0].get("op") != "approx":
        raise ValueError(f"unexpected A003 scoring contract: {task['task_id']}")
    return {
        "expected": float(checks[0]["value"]),
        "abs_tol": float(checks[0].get("abs_tol", 0.0)),
        "rel_tol": float(checks[0].get("rel_tol", 0.0)),
    }


def result_to_dict(result: Any) -> dict[str, Any]:
    return {
        "success": result.success,
        "result": result.result,
        "error": result.error,
        "error_code": result.error_code,
    }


def evaluate(task: dict[str, Any], registry: ModelRegistry,
             contracts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    params = deepcopy(task["canonical_inputs"])
    check = primary_check(task)
    tolerance = check["abs_tol"] + check["rel_tol"] * abs(check["expected"])
    executions = {tool_id: registry.invoke(tool_id, params) for tool_id in ("A002", "A003")}
    evaluations = {}
    for tool_id, result in executions.items():
        value = result.result.get("molar_mass") if result.success else None
        finite = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
        error = abs(float(value) - check["expected"]) if finite else None
        numeric_passed = bool(result.success and error is not None and error <= tolerance)
        explicit_unit = result.result.get("unit") if result.success else None
        contract_molar_mass = contracts[tool_id]["output_contract"].get("molar_mass", "")
        contract_implies_g_per_mol = "g/mol" in str(contract_molar_mass)
        primary_direct = bool(numeric_passed and explicit_unit == "g/mol")
        alternative = bool(numeric_passed and (explicit_unit == "g/mol" or contract_implies_g_per_mol))
        evaluations[tool_id] = {
            "execution": result_to_dict(result),
            "molar_mass": float(value) if finite else None,
            "absolute_error": error,
            "effective_tolerance": tolerance,
            "numeric_passed": numeric_passed,
            "explicit_unit": explicit_unit,
            "contract_implies_g_per_mol": contract_implies_g_per_mol,
            "primary_direct_acceptable": primary_direct,
            "alternative_success": alternative,
        }
    return {
        "task_id": task["task_id"],
        "formula": params["formula"],
        "expected_molar_mass": check["expected"],
        "absolute_tolerance": check["abs_tol"],
        "relative_tolerance": check["rel_tol"],
        "evaluations": evaluations,
        "a002_a003_numeric_equal": bool(
            evaluations["A002"]["molar_mass"] is not None
            and evaluations["A003"]["molar_mass"] is not None
            and math.isclose(
                evaluations["A002"]["molar_mass"],
                evaluations["A003"]["molar_mass"],
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ),
    }


def audit(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {name: common.validate_binding(binding) for name, binding in config["bindings"].items()}
    task_doc = common.load_json(paths["a003_task_registry"])
    contract_doc = common.load_json(paths["verified_contracts"])
    catalog_doc = common.load_json(paths["schema_catalog"])
    tasks = task_doc["tasks"]
    if len(tasks) != config["expected_task_count"] or len({row["task_id"] for row in tasks}) != len(tasks):
        raise ValueError("frozen A003 tasks are incomplete or duplicated")
    contracts = {row["tool_id"]: row for row in contract_doc["contracts"] if row["tool_id"] in ("A002", "A003")}
    schemas = {row["tool_id"]: row for row in catalog_doc["entries"] if row["tool_id"] in ("A002", "A003")}
    if set(contracts) != {"A002", "A003"} or set(schemas) != {"A002", "A003"}:
        raise ValueError("A002/A003 contract or schema is missing")

    registry = ModelRegistry()
    registry.discover()
    rows = [evaluate(task, registry, contracts) for task in tasks]

    revised_tasks = []
    for task, row in zip(tasks, rows):
        revised = deepcopy(task)
        revised["primary_acceptable_tools_rc2_candidate"] = deepcopy(task["revalidated_primary_acceptable_tools"])
        alternatives = set(task.get("derived_or_multi_step_neighbor_ids", []))
        if row["evaluations"]["A002"]["alternative_success"]:
            alternatives.add("A002")
        revised["alternative_success_tools_rc2_candidate"] = sorted(alternatives)
        revised["a002_primary_exclusion_reason"] = "runtime_payload_omits_explicit_unit_required_by_primary_policy"
        revised["formal_gold_mutated"] = False
        revised_tasks.append(revised)

    a002_numeric = sum(row["evaluations"]["A002"]["numeric_passed"] for row in rows)
    a002_primary = sum(row["evaluations"]["A002"]["primary_direct_acceptable"] for row in rows)
    a002_alternative = sum(row["evaluations"]["A002"]["alternative_success"] for row in rows)
    numeric_equal = sum(row["a002_a003_numeric_equal"] for row in rows)
    relation = {
        "schema_version": "1.0",
        "audit_id": config["audit_id"],
        "tool_pair": ["A002", "A003"],
        "relation_type": "asymmetric_output_overlap",
        "shared_input_contract": ["formula"],
        "shared_scientific_output": ["molar_mass"],
        "a002_additional_outputs": ["elements", "mass_fractions"],
        "a003_additional_outputs": ["unit"],
        "direction": "A002 can numerically satisfy A003 tasks; A003 cannot satisfy A002 element-count tasks",
        "independent_tool_count_recommendation": "do_not_count_as_independent_until_family_governance_review",
        "h3_role_recommendation": "asymmetric_overlap_or_alternative_success_case_not_symmetric_near_neighbor_gold",
        "formal_catalog_mutated": False,
    }
    report = {
        "schema_version": "1.0",
        "audit_id": config["audit_id"],
        "audit_status": "development_overlap_audit_complete",
        "task_count": len(rows),
        "local_tool_calls_executed": len(rows) * 2,
        "a002_numeric_pass_count": a002_numeric,
        "a002_a003_numeric_equal_count": numeric_equal,
        "a002_explicit_unit_count": sum(
            row["evaluations"]["A002"]["explicit_unit"] == "g/mol" for row in rows
        ),
        "a002_primary_direct_acceptable_count": a002_primary,
        "a002_alternative_success_count": a002_alternative,
        "primary_acceptable_sets_changed": False,
        "alternative_success_sets_expanded": a002_alternative == len(rows),
        "relation_classification": relation["relation_type"],
        "runtime_mutation_performed": False,
        "formal_catalog_mutated": False,
        "formal_gold_mutated": False,
        "external_api_calls": 0,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "interpretation": (
            "A002 reproduces A003 molar-mass values on all frozen tasks but omits an explicit unit field. "
            "Under the frozen primary policy it remains non-primary; under verified-contract semantics it is "
            "alternative success. The pair is asymmetric overlap, not two cleanly independent tools."
        ),
    }
    return {
        "rows": rows,
        "revised_tasks": revised_tasks,
        "relation": relation,
        "contracts": contracts,
        "schemas": schemas,
        "report": report,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = common.load_json(CONFIG_PATH)
    result = audit(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a002_a003_overlap_config_snapshot.json": config,
        "a002_a003_contract_snapshots.json": {"schema_version": "1.0", "tools": result["contracts"]},
        "a002_a003_schema_snapshots.json": {"schema_version": "1.0", "tools": result["schemas"]},
        "a002_a003_per_task_execution_audit.json": {"schema_version": "1.0", "rows": result["rows"]},
        "a003_acceptable_tools_rc2_candidate.json": {
            "schema_version": "1.0", "status": "candidate_not_formal_gold", "tasks": result["revised_tasks"]
        },
        "a002_a003_family_relation_candidate.json": result["relation"],
        "a002_a003_overlap_audit_report.json": result["report"],
    }
    for filename, value in artifacts.items():
        common.write_json(output_dir / filename, value)
    artifact_paths = list(output_dir.iterdir())
    common.write_json(output_dir / "artifact_manifest.json", {
        "schema_version": "1.0",
        "audit_id": config["audit_id"],
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
    return 0 if report["a002_alternative_success_count"] == report["task_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
