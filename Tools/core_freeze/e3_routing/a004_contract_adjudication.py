"""Gold-blind single-call structure gate and contract adjudicator candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("a004_contract_adjudication_config_v1.json")
ELEMENT_SYMBOLS = {
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg", "Al", "Si", "P", "S", "Cl", "Ar",
    "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "Ga", "Ge", "As", "Se", "Br", "Kr",
    "Rb", "Sr", "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn", "Sb", "Te", "I", "Xe",
    "Cs", "Ba", "La", "Ce", "Pr", "Nd", "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu",
    "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg", "Tl", "Pb", "Bi", "Po", "At", "Rn", "Fr", "Ra",
    "Ac", "Th", "Pa", "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm", "Md", "No", "Lr", "Rf", "Db",
    "Sg", "Bh", "Hs", "Mt", "Ds", "Rg", "Cn", "Nh", "Fl", "Mc", "Lv", "Ts", "Og"
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_binding(binding: dict[str, str]) -> Path:
    path = WORKSPACE / binding["path"]
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = file_hash(path)
    if actual != binding["sha256"].lower():
        raise ValueError(f"bound file hash mismatch for {path}: {actual}")
    return path


def validate_config(config: dict[str, Any]) -> None:
    if config["structure_policy"]["required_tool_call_count"] != 1:
        raise ValueError("structure gate must require exactly one call")
    for field in ("gold_access_allowed_during_decision", "tool_execution_allowed",
                  "external_api_calls_authorized", "automatic_retry_allowed",
                  "confirmatory_inference_allowed", "core_frozen"):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")
    if set(config["semantic_contract_annotations"]) != {"A004", "E3C005", "E3C027"}:
        raise ValueError("frozen adjudication profile set changed")


def first_json_object(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def is_element_or_species_label(label: str) -> bool:
    match = re.fullmatch(r"([A-Z][a-z]?)(?:[0-9]*[+-]?)?", label.strip())
    return bool(match and match.group(1) in ELEMENT_SYMBOLS)


def extract_requirements(problem_text: str) -> dict[str, Any]:
    lowered = problem_text.lower()
    if any(token in lowered for token in ("l2", "二范数", "欧氏范数")):
        normalization_kind = "l2_norm"
    elif any(token in problem_text for token in ("总和为1", "和为1", "总和为 1", "和为 1")):
        normalization_kind = "unit_sum"
    else:
        normalization_kind = "unspecified"
    mapping = first_json_object(problem_text)
    labels = list(mapping) if isinstance(mapping, dict) else []
    generic_labels_present = bool(labels) and not all(is_element_or_species_label(label) for label in labels)
    precision = None
    precision_match = re.search(r"保留\s*(\d+)\s*位", problem_text)
    if precision_match:
        precision = int(precision_match.group(1))
    return {
        "normalization_kind": normalization_kind,
        "component_mapping": mapping,
        "component_labels": labels,
        "generic_labels_present": generic_labels_present,
        "full_mapping_required": "各组分" in problem_text or "每个组分" in problem_text,
        "precision_digits": precision,
    }


def build_profile_registry(config: dict[str, Any], docs: dict[str, Any]) -> dict[str, Any]:
    verified = {row["tool_id"]: row for row in docs["verified_contracts"]["contracts"]}
    batch1 = {row["candidate_tool_id"]: row for row in docs["batch1_registry"]["candidates"]}
    batch4 = {row["candidate_tool_id"]: row for row in docs["batch4_registry"]["candidates"]}
    sources = {"A004": verified["A004"], "E3C005": batch1["E3C005"], "E3C027": batch4["E3C027"]}
    rows = []
    for tool_id, annotation in config["semantic_contract_annotations"].items():
        source = sources[tool_id]
        rows.append({
            "tool_id": tool_id,
            "source_kind": "verified_contract" if tool_id == "A004" else "registered_candidate_contract",
            "source_identity": source.get("contract_id") or source.get("provisional_candidate_id"),
            "supported_systems": deepcopy(source["supported_systems"]),
            "normalization_kind": annotation["normalization_kind"],
            "label_domain": annotation["label_domain"],
            "returns_full_mapping": annotation["returns_full_mapping"],
            "execution_eligible": annotation["execution_eligible"],
            "formal_execution_allowed": source.get("formal_execution_allowed", tool_id == "A004"),
            "source_contract_hash": source.get("contract_hash"),
        })
    return {"schema_version": "1.0", "candidate_id": config["candidate_id"],
            "profile_count": len(rows), "profiles": rows, "gold_fields_present": False}


def parse_calls(raw_response: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_response, dict) or not raw_response.get("choices"):
        return []
    message = raw_response["choices"][0].get("message", {})
    raw_calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
    calls = []
    for raw_call in raw_calls:
        function = raw_call.get("function", {})
        arguments, valid = None, False
        if isinstance(function.get("arguments"), str):
            try:
                arguments = json.loads(function["arguments"])
                valid = isinstance(arguments, dict)
            except json.JSONDecodeError:
                pass
        calls.append({"tool_id": function.get("name"), "arguments": arguments,
                      "arguments_json_valid": valid})
    return calls


def mapping_equal(left: Any, right: Any) -> bool:
    if not isinstance(left, dict) or not isinstance(right, dict) or left.keys() != right.keys():
        return False
    return all(isinstance(left[key], (int, float)) and isinstance(right[key], (int, float))
               and float(left[key]) == float(right[key]) for key in left)


def evaluate_candidate(call: dict[str, Any], requirements: dict[str, Any],
                       profiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    profile = profiles.get(call["tool_id"])
    reasons, vetoes = [], []
    if profile is None:
        vetoes.append("missing_frozen_contract_profile")
        return {"tool_id": call["tool_id"], "semantic_compatible": False,
                "execution_eligible": False, "reasons": reasons, "vetoes": vetoes}
    if not call["arguments_json_valid"]:
        vetoes.append("arguments_not_valid_json_object")
    request_mapping = requirements["component_mapping"]
    argument_mapping = (call["arguments"] or {}).get("compositions")
    if request_mapping is not None:
        if mapping_equal(argument_mapping, request_mapping):
            reasons.append("composition_arguments_match_request")
        else:
            vetoes.append("composition_arguments_do_not_match_request")
    requested_norm = requirements["normalization_kind"]
    if requested_norm != "unspecified":
        if profile["normalization_kind"] == requested_norm:
            reasons.append("normalization_kind_matches")
        else:
            vetoes.append(f"normalization_kind_mismatch:{profile['normalization_kind']}")
    if requirements["generic_labels_present"] and profile["label_domain"] == "chemical_elements_or_species":
        vetoes.append("generic_component_labels_outside_element_or_species_domain")
    else:
        reasons.append("component_label_domain_compatible")
    if requirements["full_mapping_required"]:
        if profile["returns_full_mapping"]:
            reasons.append("full_mapping_output_supported")
        else:
            vetoes.append("full_mapping_output_not_supported")
    return {"tool_id": call["tool_id"], "semantic_compatible": not vetoes,
            "execution_eligible": bool(profile["execution_eligible"] and profile["formal_execution_allowed"]),
            "reasons": reasons, "vetoes": vetoes}


def adjudicate(problem_text: str, raw_response: Any,
               profile_registry: dict[str, Any]) -> dict[str, Any]:
    requirements = extract_requirements(problem_text)
    calls = parse_calls(raw_response)
    profiles = {row["tool_id"]: row for row in profile_registry["profiles"]}
    evaluations = [evaluate_candidate(call, requirements, profiles) for call in calls]
    structure_violation = len(calls) != 1
    compatible = [row for row in evaluations if row["semantic_compatible"]]
    eligible = [row for row in compatible if row["execution_eligible"]]
    selected_tool_id = None
    selected_arguments = None
    if len(calls) == 0:
        decision, reason = "block_no_call", "no_native_tool_call"
    elif len(calls) == 1 and len(eligible) == 1:
        decision, reason = "allow_original_single_call", "single_call_contract_compatible_and_execution_eligible"
        selected_tool_id, selected_arguments = calls[0]["tool_id"], calls[0]["arguments"]
    elif len(eligible) == 1:
        decision, reason = "allow_adjudicated_single_call", "unique_contract_compatible_execution_eligible_candidate"
        selected_tool_id = eligible[0]["tool_id"]
        selected_arguments = next(call["arguments"] for call in calls if call["tool_id"] == selected_tool_id)
    else:
        decision, reason = "review_required", "contract_adjudication_not_unique"
    return {
        "requirements": requirements, "original_tool_call_count": len(calls),
        "original_called_tool_ids": [call["tool_id"] for call in calls],
        "structure_violation_detected": structure_violation,
        "original_execution_blocked": structure_violation or decision == "review_required",
        "candidate_evaluations": evaluations, "decision": decision, "decision_reason": reason,
        "selected_tool_id": selected_tool_id, "selected_arguments": selected_arguments,
        "output_tool_call_count": 1 if selected_tool_id is not None else 0,
        "tool_executed": False, "external_api_calls": 0,
    }


def offline_score(decision: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    selected = decision["selected_tool_id"]
    acceptable = gold["acceptable_tools_development_scope"]
    expected = gold["expected_parameters"]
    selection_correct = selected in acceptable and decision["output_tool_call_count"] == 1
    parameters_correct = mapping_equal(
        (decision["selected_arguments"] or {}).get("compositions"), expected.get("compositions"))
    return {"selection_correct": selection_correct, "parameters_correct": parameters_correct,
            "complete_call_correct": selection_correct and parameters_correct}


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {name: validate_binding(binding) for name, binding in config["bindings"].items()}
    docs = {name: load_json(path) for name, path in paths.items()}
    profiles = build_profile_registry(config, docs)
    task_by_id = {row["task_id"]: row for row in docs["input_tasks"]["tasks"]}
    gold_by_id = {row["task_id"]: row for row in docs["offline_scoring_registry"]["tasks"]}
    raw_rows = docs["r1_request_results"]["results"] + docs["r2r3_request_results"]["results"]
    if len(raw_rows) != 144:
        raise ValueError("replay requires all 144 frozen responses")
    decisions = []
    for raw in raw_rows:
        decision = adjudicate(task_by_id[raw["task_id"]]["problem_text"], raw["raw_response"], profiles)
        score = offline_score(decision, gold_by_id[raw["task_id"]])
        decisions.append({
            "cell_id": raw["cell_id"], "task_id": raw["task_id"],
            "model_run_repeat": raw.get("model_run_repeat", 1),
            "condition_id": raw["condition_id"], "tool_pool_size": raw["tool_pool_size"],
            "method": raw["method"], "raw_response_unchanged": True,
            **decision, "offline_evaluation_only": score,
        })
    structural = [row for row in decisions if row["structure_violation_detected"]]
    adjudicated = [row for row in decisions if row["decision"] == "allow_adjudicated_single_call"]
    original_single = [row for row in decisions if row["original_tool_call_count"] == 1]
    report = {
        "schema_version": "1.0", "candidate_id": config["candidate_id"],
        "analysis_status": "development_offline_replay_complete",
        "replayed_response_count": len(decisions),
        "original_structure_violation_count": len(structural),
        "unsafe_multi_call_execution_prevented_count": sum(row["original_execution_blocked"] for row in structural),
        "adjudicated_single_call_count": len(adjudicated),
        "review_required_count": sum(row["decision"] == "review_required" for row in decisions),
        "original_single_call_false_block_count": sum(row["decision"] != "allow_original_single_call" for row in original_single),
        "post_gate_complete_call_correct_count": sum(row["offline_evaluation_only"]["complete_call_correct"] for row in decisions),
        "post_gate_complete_call_accuracy": sum(row["offline_evaluation_only"]["complete_call_correct"] for row in decisions) / len(decisions),
        "raw_model_outcomes_modified": False,
        "tool_calls_executed": 0, "external_api_calls": 0,
        "gold_used_during_decision": False, "gold_used_for_offline_evaluation_after_decision": True,
        "independent_validation_claim_allowed": False, "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress", "core_frozen": False,
        "interpretation": "same-data development replay demonstrates candidate mechanics only; independent validation is required",
    }
    requirements = {task_id: extract_requirements(task["problem_text"]) for task_id, task in task_by_id.items()}
    safety = {
        "structure_gate": "blocks every response whose tool_call_count is not exactly one",
        "semantic_gate_inputs": ["problem_text", "native_tool_calls", "frozen_contract_profiles"],
        "semantic_gate_forbidden_inputs": ["acceptable_tools", "expected_parameters", "scoring_rule", "target_tool_id"],
        "unresolved_policy": "review_required",
        "automatic_retry_allowed": False, "tool_execution_during_replay": False,
        "limitations": [
            "contract annotations cover only A004, E3C005 and E3C027",
            "the replay set was used to develop this candidate",
            "100% replay accuracy is not an independent estimate",
            "unprofiled or non-unique compatible candidates must not be auto-executed"
        ]
    }
    return {"profiles": profiles, "requirements": requirements, "decisions": decisions,
            "structural_events": structural, "adjudicated_events": adjudicated,
            "report": report, "safety": safety}


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    built = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a004_contract_adjudication_config_snapshot.json": config,
        "a004_contract_profile_registry.json": built["profiles"],
        "a004_request_requirements.json": built["requirements"],
        "a004_replay_decisions.json": {"schema_version": "1.0", "rows": built["decisions"]},
        "a004_structure_violation_events.json": built["structural_events"],
        "a004_adjudicated_events.json": built["adjudicated_events"],
        "a004_contract_gate_report.json": built["report"],
        "a004_contract_gate_safety_boundary.json": built["safety"],
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    rows = [{"filename": path.name, "sha256": file_hash(path), "bytes": path.stat().st_size}
            for path in sorted(output_dir.iterdir(), key=lambda item: item.name)]
    write_json(output_dir / "artifact_manifest.json", {"schema_version": "1.0", "candidate_id": config["candidate_id"],
               "artifact_count": len(rows), "artifacts": rows})
    return built["report"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else WORKSPACE / args.output_dir
    print(json.dumps(build_outputs(output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
