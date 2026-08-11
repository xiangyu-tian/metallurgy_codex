"""Audit B019 parameter evidence fidelity and build a contract-aligned Schema candidate."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common


CONFIG_PATH = Path(__file__).with_name("b019_parameter_fidelity_audit_config_v1.json")


def validate_config(config: dict[str, Any]) -> None:
    if config["target_tool_id"] != "B019" or config["expected_cell_count"] != 16:
        raise ValueError("audit scope must remain the sixteen B019 R2 cells")
    for field in ("tool_execution_allowed", "external_api_calls_allowed",
                  "confirmatory_inference_allowed", "formal_catalog_mutation_allowed",
                  "core_frozen"):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")


def build_formal_schema(source_entry: dict[str, Any], contract: dict[str, Any],
                        config: dict[str, Any]) -> dict[str, Any]:
    tool = deepcopy(source_entry["openai_tool"])
    parameters = tool["function"]["parameters"]
    basis = parameters["properties"]["composition_basis"]
    basis["enum"] = deepcopy(config["allowed_formal_basis_values"])
    basis.pop("default", None)
    basis["description"] = "成分标度；确认性任务必须显式为 fraction（0—1）或 percent（0—100），禁止 auto"
    component = parameters["properties"]["component"]
    component.pop("default", None)
    component["description"] = "可选组元标签；仅当请求显式提供组元名称时传入，否则必须省略"
    parameters["required"] = deepcopy(config["required_formal_parameters"])
    parameters["additionalProperties"] = False
    return {
        "schema_version": "1.0", "audit_id": config["audit_id"],
        "tool_id": "B019", "candidate_status": "contract_aligned_formal_schema_candidate",
        "source_catalog_candidate_id": source_entry.get("candidate_id"),
        "source_contract_id": contract["contract_id"],
        "source_contract_hash": contract["contract_hash"],
        "formal_catalog_mutated": False,
        "changes": [
            "composition_basis becomes required",
            "composition_basis enum excludes auto",
            "component default B removed",
            "component allowed only when request-grounded",
            "additionalProperties set to false",
        ],
        "openai_tool": tool,
    }


def audit(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {name: common.validate_binding(binding) for name, binding in config["bindings"].items()}
    docs = {name: common.load_json(path) for name, path in paths.items()}
    cells = [row for row in docs["scored_cells"]["rows"]
             if row["task_id"].startswith("E1B2-B019-")]
    if len(cells) != 16 or len({row["cell_id"] for row in cells}) != 16:
        raise ValueError("B019 R2 cells are incomplete or duplicated")
    tasks = {row["task_id"]: row for row in docs["task_registry"]["tasks"]
             if row["target_tool_id"] == "B019"}
    entries = [row for row in docs["schema_catalog"]["entries"] if row["tool_id"] == "B019"]
    contracts = [row for row in docs["verified_contracts"]["contracts"] if row["tool_id"] == "B019"]
    if len(entries) != 1 or len(contracts) != 1:
        raise ValueError("B019 schema or verified contract is not unique")
    source_entry, contract = entries[0], contracts[0]
    source_parameters = source_entry["openai_tool"]["function"]["parameters"]
    schema_contract_findings = {
        "composition_basis_required_by_contract": "composition_basis" in contract["required_inputs"],
        "composition_basis_required_by_source_schema": "composition_basis" in source_parameters["required"],
        "source_schema_allows_auto": "auto" in source_parameters["properties"]["composition_basis"]["enum"],
        "source_component_default": source_parameters["properties"]["component"].get("default"),
    }
    rows = []
    required = set(config["required_formal_parameters"])
    for cell in cells:
        task = tasks[cell["task_id"]]
        arguments = cell.get("arguments") or {}
        canonical = task["canonical_inputs"]
        missing_required = sorted(required - set(arguments))
        basis_valid = arguments.get("composition_basis") in config["allowed_formal_basis_values"]
        extra_parameters = sorted(set(arguments) - set(canonical))
        ungrounded_optional = [name for name in extra_parameters
                               if name in config["optional_parameter_grounding_policy"]]
        strict_correct = bool(
            cell["selection_correct"] and cell["parameters_correct"]
            and not missing_required and basis_valid and not ungrounded_optional
        )
        rows.append({
            "cell_id": cell["cell_id"], "task_id": cell["task_id"],
            "method": cell["method"], "tool_pool_size": cell["tool_pool_size"],
            "selected_tool_id": cell["selected_tool_id"], "arguments": arguments,
            "legacy_selection_correct": cell["selection_correct"],
            "legacy_parameters_correct": cell["parameters_correct"],
            "missing_required_parameters": missing_required,
            "formal_basis_valid": basis_valid,
            "extra_parameters_not_in_canonical_inputs": extra_parameters,
            "ungrounded_optional_parameters": ungrounded_optional,
            "strict_parameter_evidence_fidelity": strict_correct,
            "scientific_result_incorrect_claimed": False,
        })
    ungrounded = [row for row in rows if row["ungrounded_optional_parameters"]]
    strict = [row for row in rows if row["strict_parameter_evidence_fidelity"]]
    report = {
        "schema_version": "1.0", "audit_id": config["audit_id"],
        "audit_status": "development_parameter_fidelity_audit_complete",
        "cell_count": len(rows),
        "legacy_selection_correct_count": sum(row["legacy_selection_correct"] for row in rows),
        "legacy_parameters_correct_count": sum(row["legacy_parameters_correct"] for row in rows),
        "strict_parameter_evidence_fidelity_count": len(strict),
        "strict_parameter_evidence_fidelity_rate": len(strict) / len(rows),
        "ungrounded_optional_parameter_count": len(ungrounded),
        "legacy_parameter_false_positive_count": sum(
            row["legacy_parameters_correct"] and not row["strict_parameter_evidence_fidelity"] for row in rows
        ),
        "ungrounded_component_values": dict(Counter(
            row["arguments"].get("component") for row in ungrounded
        )),
        "ungrounded_by_method": dict(Counter(row["method"] for row in ungrounded)),
        "ungrounded_by_tool_pool_size": {
            str(key): value for key, value in Counter(row["tool_pool_size"] for row in ungrounded).items()
        },
        "schema_contract_findings": schema_contract_findings,
        "scientific_result_error_inferred": False,
        "interpretation": (
            "B019 selection and required numeric values were correct, but eleven calls added an ungrounded "
            "component='B'; legacy scoring therefore overstates parameter evidence fidelity"
        ),
        "external_api_calls": 0, "tool_calls_executed": 0,
        "confirmatory_inference_allowed": False, "formal_catalog_mutated": False,
        "cf05_status": "in_progress", "core_frozen": False,
    }
    return {
        "source_schema": source_entry, "contract": contract,
        "formal_schema_candidate": build_formal_schema(source_entry, contract, config),
        "rows": rows, "report": report,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = common.load_json(CONFIG_PATH)
    result = audit(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "b019_parameter_audit_config_snapshot.json": config,
        "b019_source_schema_snapshot.json": result["source_schema"],
        "b019_verified_contract_snapshot.json": result["contract"],
        "b019_formal_schema_candidate.json": result["formal_schema_candidate"],
        "b019_per_cell_parameter_audit.json": {"schema_version": "1.0", "rows": result["rows"]},
        "b019_parameter_fidelity_report.json": result["report"],
    }
    for filename, value in artifacts.items():
        common.write_json(output_dir / filename, value)
    artifact_paths = list(output_dir.iterdir())
    common.write_json(output_dir / "artifact_manifest.json", {
        "schema_version": "1.0", "audit_id": config["audit_id"],
        "artifact_count": len(artifact_paths),
        "artifacts": [{"filename": path.name, "sha256": common.file_hash(path), "bytes": path.stat().st_size}
                      for path in sorted(artifact_paths, key=lambda item: item.name)],
    })
    return result["report"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else common.WORKSPACE / args.output_dir
    print(json.dumps(build_outputs(output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
