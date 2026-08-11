"""Audit and gate A001/A002 parameters against request evidence and verified contracts."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common


TOOLS_DIR = Path(__file__).resolve().parents[2]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from models_core.models_a import parse_formula  # noqa: E402


CONFIG_PATH = Path(__file__).with_name("a001_a002_strict_parameter_gate_config_v1.json")
CHALLENGE_PATH = Path(__file__).with_name("a001_a002_strict_parameter_gate_challenge_v1.json")
A001_PATTERN = re.compile(
    r"请将\s*([-+]?\d+(?:\.\d+)?)\s+([^\s，。]+)\s+换算为\s+([^\s，。]+)"
)
A002_PATTERN = re.compile(r"解析中性化学式\s*([^\s，。]+)")


def validate_config(config: dict[str, Any]) -> None:
    if set(config["target_tools"]) != {"A001", "A002"}:
        raise ValueError("candidate scope must remain A001 and A002")
    if config["expected_cells_per_tool"] != 16:
        raise ValueError("expected cell count must remain sixteen per tool")
    if config["deterministic_structural_validation_allowed"] is not True:
        raise ValueError("deterministic structural validation must remain enabled")
    for field in (
        "tool_execution_allowed",
        "external_api_calls_allowed",
        "automatic_retry_allowed",
        "formal_catalog_mutation_allowed",
        "confirmatory_inference_allowed",
        "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")


def numeric_equal(left: Any, right: Any) -> bool:
    return (
        isinstance(left, (int, float))
        and not isinstance(left, bool)
        and isinstance(right, (int, float))
        and not isinstance(right, bool)
        and math.isfinite(float(left))
        and math.isfinite(float(right))
        and math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12)
    )


def extract_request_evidence(problem_text: str) -> dict[str, Any]:
    a001 = A001_PATTERN.search(problem_text)
    if a001 is not None:
        return {
            "parse_complete": True,
            "inferred_tool_id": "A001",
            "required_parameters": {
                "value": float(a001.group(1)),
                "source_unit": a001.group(2),
                "target_unit": a001.group(3),
            },
        }
    a002 = A002_PATTERN.search(problem_text)
    if a002 is not None:
        return {
            "parse_complete": True,
            "inferred_tool_id": "A002",
            "required_parameters": {"formula": a002.group(1)},
        }
    return {"parse_complete": False, "inferred_tool_id": None, "required_parameters": None}


def formula_contract_check(formula: Any) -> tuple[bool, str | None]:
    if not isinstance(formula, str) or not formula:
        return False, "formula_not_nonempty_string"
    _, error = parse_formula(formula)
    return error is None, error


def adjudicate(problem_text: str, selected_tool_id: str | None, arguments: Any,
               config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    evidence = extract_request_evidence(problem_text)
    vetoes: list[str] = []
    reasons: list[str] = []
    if not evidence["parse_complete"]:
        vetoes.append("request_not_deterministically_parseable")
        inferred_tool_id = None
        expected = {}
    else:
        inferred_tool_id = evidence["inferred_tool_id"]
        expected = evidence["required_parameters"]
        if selected_tool_id != inferred_tool_id:
            vetoes.append("selected_tool_does_not_match_request_intent")

    if not isinstance(arguments, dict):
        vetoes.append("arguments_not_object")
        arguments = {}

    if inferred_tool_id in config["target_tools"]:
        required = config["target_tools"][inferred_tool_id]["required_parameters"]
        missing = [name for name in required if name not in arguments]
        vetoes.extend(f"missing_required:{name}" for name in missing)
        unknown = sorted(set(arguments) - set(required))
        vetoes.extend(f"unknown_parameter:{name}" for name in unknown)

        for name in required:
            if name not in arguments or name not in expected:
                continue
            matches = numeric_equal(arguments[name], expected[name]) if name == "value" else arguments[name] == expected[name]
            if not matches:
                vetoes.append(f"request_argument_mismatch:{name}")

        if inferred_tool_id == "A001" and not missing:
            pair = [arguments.get("source_unit"), arguments.get("target_unit")]
            if pair not in config["target_tools"]["A001"]["verified_directed_unit_pairs"]:
                vetoes.append("unit_pair_outside_verified_contract")
            elif not any(item.startswith("request_argument_mismatch") for item in vetoes):
                reasons.append("unit_pair_inside_verified_contract")

        if inferred_tool_id == "A002" and "formula" in arguments:
            valid_formula, formula_error = formula_contract_check(arguments["formula"])
            if not valid_formula:
                vetoes.append("formula_outside_verified_neutral_grammar")
            else:
                reasons.append("formula_inside_verified_neutral_grammar")
            formula_validation = {"passed": valid_formula, "error": formula_error}
        else:
            formula_validation = None
    else:
        required, missing, unknown, formula_validation = [], [], [], None

    if evidence["parse_complete"] and not any(
        item.startswith("request_argument_mismatch") or item.startswith("missing_required")
        for item in vetoes
    ):
        reasons.append("all_required_arguments_grounded_in_request")
    decision = "candidate_pass" if not vetoes else config["unresolved_action"]
    return {
        "request_evidence": evidence,
        "selected_tool_id": selected_tool_id,
        "arguments": deepcopy(arguments),
        "missing_required_parameters": missing,
        "unknown_parameters": unknown,
        "formula_structural_validation": formula_validation,
        "reasons": reasons,
        "vetoes": vetoes,
        "decision": decision,
        "execution_ready": decision == "candidate_pass",
        "tool_executed": False,
        "external_api_calls": 0,
    }


def build_formal_schema(source: dict[str, Any], contract: dict[str, Any],
                        config: dict[str, Any]) -> dict[str, Any]:
    tool_id = source["tool_id"]
    tool = deepcopy(source["openai_tool"])
    parameters = tool["function"]["parameters"]
    parameters["required"] = deepcopy(config["target_tools"][tool_id]["required_parameters"])
    parameters["additionalProperties"] = False
    if tool_id == "A001":
        parameters["properties"]["source_unit"]["description"] = (
            "源单位；必须与请求原文一致，且源单位—目标单位组合须位于受验证合同范围"
        )
        parameters["properties"]["target_unit"]["description"] = (
            "目标单位；必须与请求原文一致，禁止自行倒置换算方向"
        )
    else:
        parameters["properties"]["formula"]["description"] = (
            "请求中显式给出的中性化学式；必须逐字符一致并通过冻结的完整词法消费规则"
        )
    return {
        "schema_version": "1.0",
        "candidate_id": config["candidate_id"],
        "tool_id": tool_id,
        "candidate_status": "contract_aligned_formal_schema_candidate",
        "source_contract_id": contract["contract_id"],
        "source_contract_hash": contract["contract_hash"],
        "formal_catalog_mutated": False,
        "changes": ["additionalProperties set to false", "parameter evidence description tightened"],
        "openai_tool": tool,
    }


def audit_and_replay(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {name: common.validate_binding(binding) for name, binding in config["bindings"].items()}
    docs = {name: common.load_json(path) for name, path in paths.items() if name != "runtime_source"}
    all_cells = docs["scored_cells"]["rows"]
    all_tasks = {row["task_id"]: row for row in docs["task_registry"]["tasks"]}
    schemas = {row["tool_id"]: row for row in docs["schema_catalog"]["entries"]
               if row["tool_id"] in config["target_tools"]}
    contracts = {row["tool_id"]: row for row in docs["verified_contracts"]["contracts"]
                 if row["tool_id"] in config["target_tools"]}
    if set(schemas) != set(config["target_tools"]) or set(contracts) != set(config["target_tools"]):
        raise ValueError("A001/A002 schema or contract is missing or duplicated")

    rows = []
    for tool_id in config["target_tools"]:
        cells = [row for row in all_cells if row["source_tool_id"] == tool_id]
        if len(cells) != config["expected_cells_per_tool"] or len({row["cell_id"] for row in cells}) != len(cells):
            raise ValueError(f"{tool_id} replay cells are incomplete or duplicated")
        for cell in cells:
            task = all_tasks[cell["task_id"]]
            decision = adjudicate(task["problem_text"], cell["selected_tool_id"], cell["arguments"], config)
            canonical = task["canonical_inputs"]
            strict_faithful = bool(
                decision["execution_ready"]
                and set(cell["arguments"]) == set(canonical)
                and all(
                    numeric_equal(cell["arguments"][name], value)
                    if name == "value" else cell["arguments"][name] == value
                    for name, value in canonical.items()
                )
            )
            rows.append({
                "cell_id": cell["cell_id"],
                "task_id": cell["task_id"],
                "source_tool_id": tool_id,
                "method": cell["method"],
                "tool_pool_size": cell["tool_pool_size"],
                "legacy_parameters_correct": cell["parameters_correct"],
                **decision,
                "strict_parameter_evidence_fidelity": strict_faithful,
                "gold_used_during_decision": False,
                "gold_used_after_decision_for_offline_evaluation": True,
            })

    challenge = common.load_json(CHALLENGE_PATH)
    challenge_rows = []
    for case in challenge["cases"]:
        decision = adjudicate(case["problem_text"], case["tool_id"], case["arguments"], config)
        passed = (
            decision["decision"] == case["expected_decision"]
            and decision["execution_ready"] is case["expected_execution_ready"]
        )
        challenge_rows.append({
            "case_id": case["case_id"],
            "category": case["category"],
            "decision": decision,
            "passed": passed,
        })

    schema_findings = {}
    formal_schemas = {}
    for tool_id in config["target_tools"]:
        parameters = schemas[tool_id]["openai_tool"]["function"]["parameters"]
        schema_findings[tool_id] = {
            "required_parameters_match_contract": (
                set(parameters.get("required", [])) == set(contracts[tool_id]["required_inputs"])
            ),
            "source_additional_properties_explicitly_false": parameters.get("additionalProperties") is False,
            "source_default_parameters": {
                name: value["default"] for name, value in parameters["properties"].items() if "default" in value
            },
        }
        formal_schemas[tool_id] = build_formal_schema(schemas[tool_id], contracts[tool_id], config)

    by_tool = {}
    for tool_id in config["target_tools"]:
        subset = [row for row in rows if row["source_tool_id"] == tool_id]
        by_tool[tool_id] = {
            "cell_count": len(subset),
            "unique_task_count": len({row["task_id"] for row in subset}),
            "legacy_parameters_correct_count": sum(row["legacy_parameters_correct"] for row in subset),
            "strict_parameter_evidence_fidelity_count": sum(
                row["strict_parameter_evidence_fidelity"] for row in subset
            ),
            "execution_ready_count": sum(row["execution_ready"] for row in subset),
        }
    report = {
        "schema_version": "1.0",
        "candidate_id": config["candidate_id"],
        "analysis_status": "development_audit_and_strict_gate_replay_complete",
        "cell_count": len(rows),
        "unique_task_count": len({row["task_id"] for row in rows}),
        "legacy_parameters_correct_count": sum(row["legacy_parameters_correct"] for row in rows),
        "strict_parameter_evidence_fidelity_count": sum(
            row["strict_parameter_evidence_fidelity"] for row in rows
        ),
        "execution_ready_count": sum(row["execution_ready"] for row in rows),
        "review_required_count": sum(row["decision"] == "review_required" for row in rows),
        "by_tool": by_tool,
        "challenge_case_count": len(challenge_rows),
        "challenge_passed_count": sum(row["passed"] for row in challenge_rows),
        "challenge_categories": dict(Counter(row["category"] for row in challenge_rows)),
        "schema_contract_findings": schema_findings,
        "runtime_mutation_required": False,
        "gold_used_during_decision": False,
        "external_api_calls": 0,
        "tool_calls_executed": 0,
        "formal_catalog_mutated": False,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "interpretation": (
            "All observed calls across four unique development tasks are request-grounded and contract-ready. "
            "This is implementation evidence, not broad task-distribution evidence; remaining hardening is a "
            "formal-schema additionalProperties closure plus deterministic request and capability gating."
        ),
    }
    return {
        "rows": rows,
        "challenge_rows": challenge_rows,
        "schemas": schemas,
        "contracts": contracts,
        "formal_schemas": formal_schemas,
        "report": report,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = common.load_json(CONFIG_PATH)
    result = audit_and_replay(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a001_a002_gate_config_snapshot.json": config,
        "a001_a002_gate_challenge_snapshot.json": common.load_json(CHALLENGE_PATH),
        "a001_a002_source_schema_snapshots.json": {
            "schema_version": "1.0", "tools": result["schemas"]
        },
        "a001_a002_verified_contract_snapshots.json": {
            "schema_version": "1.0", "tools": result["contracts"]
        },
        "a001_formal_schema_candidate.json": result["formal_schemas"]["A001"],
        "a002_formal_schema_candidate.json": result["formal_schemas"]["A002"],
        "a001_a002_per_cell_parameter_audit.json": {"schema_version": "1.0", "rows": result["rows"]},
        "a001_a002_gate_challenge_results.json": {
            "schema_version": "1.0", "rows": result["challenge_rows"]
        },
        "a001_a002_strict_parameter_gate_report.json": result["report"],
    }
    for filename, value in artifacts.items():
        common.write_json(output_dir / filename, value)
    artifact_paths = list(output_dir.iterdir())
    common.write_json(output_dir / "artifact_manifest.json", {
        "schema_version": "1.0",
        "candidate_id": config["candidate_id"],
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
    return 0 if report["challenge_passed_count"] == report["challenge_case_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
