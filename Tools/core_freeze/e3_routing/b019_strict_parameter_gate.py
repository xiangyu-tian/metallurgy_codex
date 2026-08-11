"""Gold-blind strict parameter gate candidate for B019 lever-rule calls."""

from __future__ import annotations

import argparse
import json
import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common


CONFIG_PATH = Path(__file__).with_name("b019_strict_parameter_gate_config_v1.json")
CHALLENGE_PATH = Path(__file__).with_name("b019_strict_parameter_gate_challenge_v1.json")
REQUEST_PATTERN = re.compile(
    r"总体成分为\s*([-+]?\d+(?:\.\d+)?)，相1边界成分为\s*([-+]?\d+(?:\.\d+)?)，"
    r"相2边界成分为\s*([-+]?\d+(?:\.\d+)?)，三者均使用\s*(fraction|percent)\s*标度"
)
COMPONENT_PATTERN = re.compile(r"(?:指定)?组元为\s*([A-Za-z][A-Za-z0-9_-]*)")


def validate_config(config: dict[str, Any]) -> None:
    for field in ("tool_execution_allowed", "external_api_calls_allowed",
                  "automatic_retry_allowed", "runtime_default_component_remediated",
                  "confirmatory_inference_allowed", "formal_catalog_mutation_allowed",
                  "core_frozen"):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")


def extract_request_evidence(problem_text: str) -> dict[str, Any]:
    match = REQUEST_PATTERN.search(problem_text)
    component = COMPONENT_PATTERN.search(problem_text)
    if match is None:
        return {"parse_complete": False, "required_parameters": None,
                "explicit_component": component.group(1) if component else None,
                "physical_boundary_valid": False, "physical_vetoes": ["request_not_deterministically_parseable"]}
    overall, phase1, phase2 = (float(match.group(index)) for index in range(1, 4))
    basis = match.group(4)
    upper = 1.0 if basis == "fraction" else 100.0
    vetoes = []
    if not all(math.isfinite(value) and 0.0 <= value <= upper for value in (overall, phase1, phase2)):
        vetoes.append("composition_outside_declared_basis_range")
    if math.isclose(phase1, phase2, rel_tol=0.0, abs_tol=1e-12):
        vetoes.append("phase_endpoints_not_distinct")
    if not min(phase1, phase2) <= overall <= max(phase1, phase2):
        vetoes.append("overall_composition_outside_tieline")
    return {
        "parse_complete": True,
        "required_parameters": {
            "overall_composition": overall, "phase1_composition": phase1,
            "phase2_composition": phase2, "composition_basis": basis,
        },
        "explicit_component": component.group(1) if component else None,
        "physical_boundary_valid": not vetoes, "physical_vetoes": vetoes,
    }


def numeric_equal(left: Any, right: Any) -> bool:
    return (isinstance(left, (int, float)) and not isinstance(left, bool)
            and isinstance(right, (int, float)) and not isinstance(right, bool)
            and math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12))


def adjudicate(problem_text: str, tool_id: str | None, arguments: Any,
               config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    evidence = extract_request_evidence(problem_text)
    vetoes = list(evidence["physical_vetoes"])
    reasons = []
    sanitized = deepcopy(arguments) if isinstance(arguments, dict) else None
    if tool_id != "B019":
        vetoes.append("selected_tool_is_not_b019")
    if not isinstance(arguments, dict):
        vetoes.append("arguments_not_object")
        arguments = {}
    required = config["required_parameters"]
    missing = [name for name in required if name not in arguments]
    if missing:
        vetoes.extend(f"missing_required:{name}" for name in missing)
    if evidence["parse_complete"]:
        expected = evidence["required_parameters"]
        for name in required:
            if name not in arguments:
                continue
            if name == "composition_basis":
                if arguments[name] != expected[name] or arguments[name] not in config["allowed_basis_values"]:
                    vetoes.append("composition_basis_not_explicit_or_mismatch")
            elif not numeric_equal(arguments[name], expected[name]):
                vetoes.append(f"request_argument_mismatch:{name}")
        if not any(item.startswith("request_argument_mismatch") or item.startswith("missing_required")
                   or item == "composition_basis_not_explicit_or_mismatch" for item in vetoes):
            reasons.append("all_required_arguments_grounded_in_request")
    allowed = set(required) | set(config["grounded_optional_parameters"])
    unknown = sorted(set(arguments) - allowed)
    if unknown:
        vetoes.extend(f"unknown_parameter:{name}" for name in unknown)
    explicit_component = evidence["explicit_component"]
    component_present = "component" in arguments
    optional_elided = []
    if explicit_component is not None:
        if not component_present:
            vetoes.append("explicit_component_missing_from_arguments")
        elif arguments["component"] != explicit_component:
            vetoes.append("component_not_grounded_in_request")
        else:
            reasons.append("component_grounded_in_request")
    elif component_present:
        optional_elided.append("component")
        if isinstance(sanitized, dict):
            sanitized.pop("component", None)
        reasons.append("ungrounded_optional_component_elided")
    runtime_default_risk = explicit_component is None
    if vetoes:
        decision, candidate_arguments = "review_required", None
    elif optional_elided:
        decision, candidate_arguments = "candidate_pass_after_optional_elision", sanitized
    else:
        decision, candidate_arguments = "candidate_pass_original_parameters", sanitized
    execution_ready = bool(not vetoes and not runtime_default_risk)
    return {
        "request_evidence": evidence, "tool_id": tool_id,
        "original_arguments": deepcopy(arguments), "candidate_arguments": candidate_arguments,
        "optional_parameters_elided": optional_elided, "reasons": reasons, "vetoes": vetoes,
        "decision": decision,
        "original_execution_blocked": decision != "candidate_pass_original_parameters" or not execution_ready,
        "runtime_default_component_risk": runtime_default_risk,
        "execution_ready": execution_ready, "tool_executed": False, "external_api_calls": 0,
    }


def replay(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {name: common.validate_binding(binding) for name, binding in config["bindings"].items()}
    docs = {name: common.load_json(path) for name, path in paths.items()}
    cells = [row for row in docs["scored_cells"]["rows"] if row["task_id"].startswith("E1B2-B019-")]
    tasks = {row["task_id"]: row for row in docs["task_registry"]["tasks"] if row["target_tool_id"] == "B019"}
    rows = []
    for cell in cells:
        decision = adjudicate(tasks[cell["task_id"]]["problem_text"], cell["selected_tool_id"], cell["arguments"], config)
        canonical = tasks[cell["task_id"]]["canonical_inputs"]
        candidate = decision["candidate_arguments"] or {}
        candidate_faithful = (
            all(name in candidate for name in config["required_parameters"])
            and all(numeric_equal(candidate[name], canonical[name]) if name != "composition_basis"
                    else candidate[name] == canonical[name] for name in config["required_parameters"])
            and set(candidate).issubset(set(canonical))
        )
        rows.append({
            "cell_id": cell["cell_id"], "task_id": cell["task_id"],
            "method": cell["method"], "tool_pool_size": cell["tool_pool_size"],
            **decision, "offline_candidate_parameter_faithful": candidate_faithful,
            "gold_used_during_decision": False,
        })
    challenge = common.load_json(CHALLENGE_PATH)
    challenge_rows = []
    for case in challenge["cases"]:
        decision = adjudicate(case["problem_text"], case["tool_id"], case["arguments"], config)
        passed = (decision["decision"] == case["expected_decision"]
                  and decision["execution_ready"] is case["expected_execution_ready"])
        challenge_rows.append({"case_id": case["case_id"], "category": case["category"],
                               "decision": decision, "passed": passed})
    report = {
        "schema_version": "1.0", "candidate_id": config["candidate_id"],
        "analysis_status": "offline_replay_and_boundary_challenge_complete",
        "replay_cell_count": len(rows),
        "original_parameter_faithful_count": sum(row["decision"] == "candidate_pass_original_parameters" for row in rows),
        "optional_elision_count": sum(row["decision"] == "candidate_pass_after_optional_elision" for row in rows),
        "review_required_count": sum(row["decision"] == "review_required" for row in rows),
        "candidate_parameter_faithful_count": sum(row["offline_candidate_parameter_faithful"] for row in rows),
        "execution_ready_count": sum(row["execution_ready"] for row in rows),
        "runtime_default_component_risk_count": sum(row["runtime_default_component_risk"] for row in rows),
        "challenge_case_count": len(challenge_rows),
        "challenge_passed_count": sum(row["passed"] for row in challenge_rows),
        "external_api_calls": 0, "tool_calls_executed": 0,
        "gold_used_during_decision": False, "gold_used_after_decision_for_offline_evaluation": True,
        "formal_catalog_mutated": False, "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress", "core_frozen": False,
        "interpretation": (
            "parameter candidates become request-faithful after optional elision, but execution remains blocked "
            "because the current B019 runtime still defaults an omitted component to B"
        ),
    }
    return {"rows": rows, "challenge_rows": challenge_rows, "report": report}


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = common.load_json(CONFIG_PATH)
    result = replay(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "b019_parameter_gate_config_snapshot.json": config,
        "b019_parameter_gate_challenge_snapshot.json": common.load_json(CHALLENGE_PATH),
        "b019_parameter_gate_replay_decisions.json": {"schema_version": "1.0", "rows": result["rows"]},
        "b019_parameter_gate_challenge_results.json": {"schema_version": "1.0", "rows": result["challenge_rows"]},
        "b019_parameter_gate_report.json": result["report"],
    }
    for filename, value in artifacts.items():
        common.write_json(output_dir / filename, value)
    artifact_paths = list(output_dir.iterdir())
    common.write_json(output_dir / "artifact_manifest.json", {
        "schema_version": "1.0", "candidate_id": config["candidate_id"],
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
