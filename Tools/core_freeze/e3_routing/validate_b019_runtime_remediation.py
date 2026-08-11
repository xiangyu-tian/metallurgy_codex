"""Validate the B019 no-implicit-component runtime remediation locally."""

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


CONFIG_PATH = Path(__file__).with_name("b019_runtime_remediation_validation_config_v1.json")


def validate_config(config: dict[str, Any]) -> None:
    if config["local_deterministic_tool_execution_allowed"] is not True:
        raise ValueError("local deterministic tool execution must be explicitly allowed")
    for field in (
        "external_api_calls_allowed",
        "automatic_retry_allowed",
        "formal_catalog_mutation_allowed",
        "confirmatory_inference_allowed",
        "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")


def expected_result(arguments: dict[str, Any]) -> dict[str, float]:
    overall = float(arguments["overall_composition"])
    phase1 = float(arguments["phase1_composition"])
    phase2 = float(arguments["phase2_composition"])
    return {
        "phase1_fraction": (phase2 - overall) / (phase2 - phase1),
        "phase2_fraction": (overall - phase1) / (phase2 - phase1),
    }


def invoke_and_check(registry: ModelRegistry, arguments: dict[str, Any]) -> dict[str, Any]:
    result = registry.invoke("B019", arguments)
    expected = expected_result(arguments) if result.success else None
    numeric_passed = bool(
        result.success
        and math.isclose(result.result["phase1_fraction"], expected["phase1_fraction"], abs_tol=1e-6)
        and math.isclose(result.result["phase2_fraction"], expected["phase2_fraction"], abs_tol=1e-6)
        and result.result["conservation_passed"] is True
    )
    component = result.result.get("component") if result.success else None
    expected_status = "explicit" if arguments.get("component") not in (None, "") else "unspecified"
    grounding_passed = bool(
        result.success
        and component == arguments.get("component")
        and result.result.get("component_grounding_status") == expected_status
    )
    return {
        "arguments": arguments,
        "success": result.success,
        "error_code": result.error_code,
        "result": result.result,
        "numeric_invariants_passed": numeric_passed,
        "component_grounding_passed": grounding_passed,
        "passed": numeric_passed and grounding_passed,
    }


def validate(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {name: common.validate_binding(binding) for name, binding in config["bindings"].items()}
    decisions = common.load_json(paths["strict_gate_decisions"])["rows"]
    if len(decisions) != config["expected_replay_cell_count"]:
        raise ValueError("unexpected strict-gate replay cell count")

    registry = ModelRegistry()
    registry.discover()
    model = registry.get("B019")
    component_schema = next(field.to_dict() for field in model.input_fields if field.name == "component")
    if "default" in component_schema:
        raise ValueError("B019 component schema still exposes an implicit default")

    replay_rows = []
    for row in decisions:
        arguments = row.get("candidate_arguments")
        if not isinstance(arguments, dict):
            raise ValueError(f"missing candidate arguments for {row['cell_id']}")
        check = invoke_and_check(registry, arguments)
        replay_rows.append({
            "cell_id": row["cell_id"],
            "task_id": row["task_id"],
            "method": row["method"],
            "tool_pool_size": row["tool_pool_size"],
            **check,
        })

    boundary_cases = [
        {
            "case_id": "B019-RUNTIME-OMITTED-COMPONENT",
            "arguments": {"overall_composition": 0.4, "phase1_composition": 0.2,
                          "phase2_composition": 0.7, "composition_basis": "fraction"},
            "expected_success": True,
        },
        {
            "case_id": "B019-RUNTIME-EXPLICIT-COMPONENT",
            "arguments": {"overall_composition": 0.4, "phase1_composition": 0.2,
                          "phase2_composition": 0.7, "composition_basis": "fraction", "component": "Fe"},
            "expected_success": True,
        },
        {
            "case_id": "B019-RUNTIME-PERCENT",
            "arguments": {"overall_composition": 40, "phase1_composition": 20,
                          "phase2_composition": 70, "composition_basis": "percent"},
            "expected_success": True,
        },
        {
            "case_id": "B019-RUNTIME-OUTSIDE-TIELINE",
            "arguments": {"overall_composition": 0.9, "phase1_composition": 0.2,
                          "phase2_composition": 0.7, "composition_basis": "fraction"},
            "expected_success": False,
        },
    ]
    boundary_rows = []
    for case in boundary_cases:
        result = registry.invoke("B019", case["arguments"])
        passed = result.success is case["expected_success"]
        if result.success:
            passed = passed and invoke_and_check(registry, case["arguments"])["passed"]
        boundary_rows.append({
            **case,
            "observed_success": result.success,
            "error_code": result.error_code,
            "passed": passed,
        })

    replay_passed = sum(row["passed"] for row in replay_rows)
    boundary_passed = sum(row["passed"] for row in boundary_rows)
    report = {
        "schema_version": "1.0",
        "validation_id": config["validation_id"],
        "validation_status": (
            "passed"
            if replay_passed == len(replay_rows) and boundary_passed == len(boundary_rows)
            else "failed"
        ),
        "runtime_version": model.version,
        "component_schema_default_absent": "default" not in component_schema,
        "replay_cell_count": len(replay_rows),
        "replay_passed_count": replay_passed,
        "implicit_component_output_count": sum(
            row["result"].get("component") == "B" and "component" not in row["arguments"]
            for row in replay_rows if row["success"]
        ),
        "unspecified_component_output_count": sum(
            row["result"].get("component") is None
            and row["result"].get("component_grounding_status") == "unspecified"
            for row in replay_rows if row["success"]
        ),
        "boundary_case_count": len(boundary_rows),
        "boundary_passed_count": boundary_passed,
        "local_tool_calls_executed": len(replay_rows) + len(boundary_rows),
        "external_api_calls": 0,
        "formal_catalog_mutated": False,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "interpretation": (
            "The runtime no longer invents component B when the request omits a component; "
            "the strict formal overlay still requires an explicit fraction or percent basis."
        ),
    }
    return {"replay_rows": replay_rows, "boundary_rows": boundary_rows, "report": report}


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = common.load_json(CONFIG_PATH)
    result = validate(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "b019_runtime_remediation_config_snapshot.json": config,
        "b019_runtime_remediation_replay.json": {"schema_version": "1.0", "rows": result["replay_rows"]},
        "b019_runtime_remediation_boundary_results.json": {
            "schema_version": "1.0", "rows": result["boundary_rows"]
        },
        "b019_runtime_remediation_report.json": result["report"],
    }
    for filename, value in artifacts.items():
        common.write_json(output_dir / filename, value)
    artifact_paths = list(output_dir.iterdir())
    common.write_json(output_dir / "artifact_manifest.json", {
        "schema_version": "1.0",
        "validation_id": config["validation_id"],
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
    return 0 if report["validation_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
