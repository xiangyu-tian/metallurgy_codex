"""Deterministic structural layer and merge logic for E2 hybrid gate v1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
BASE_POLICY_PATH = HERE / "policy_v1.json"
HYBRID_POLICY_PATH = HERE / "hybrid_gate_policy_v1.json"
SEMANTIC_SCHEMA_PATH = HERE / "output_schema_hybrid_semantic_v1.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def contains_explicit_ambiguity(value: Any) -> bool:
    if isinstance(value, dict):
        candidates = value.get("candidates")
        if (
            value.get("status") == "ambiguous"
            and isinstance(candidates, list)
            and bool(candidates)
        ):
            return True
        return any(contains_explicit_ambiguity(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_explicit_ambiguity(item) for item in value)
    return False


def derive_structural_flags(
    structured_state: dict[str, Any],
    contract: dict[str, Any],
    hybrid_policy: dict[str, Any],
) -> list[str]:
    parameters = structured_state.get("parameters")
    if not isinstance(parameters, dict):
        parameters = {}
    request_context = structured_state.get("request_context")
    if not isinstance(request_context, dict):
        request_context = {}
    flags: set[str] = set()
    if any(
        required not in parameters
        for required in contract["required_inputs"]
    ):
        flags.add("missing_parameter")
    if contains_explicit_ambiguity(parameters):
        flags.add("ambiguous_parameter")
    if structured_state.get("service_status") == "unavailable":
        flags.add("unavailable")
    requested_version = request_context.get("requested_tool_version")
    contract_version = contract.get("tool_version")
    if (
        requested_version is not None
        and contract_version is not None
        and requested_version != contract_version
    ):
        flags.add("version_mismatch")
    structural = set(hybrid_policy["structural_flags"])
    if not flags <= structural:
        raise ValueError("structural checker emitted a semantic flag")
    return [
        flag
        for flag in hybrid_policy["flag_order"]
        if flag in flags
    ]


def validate_semantic_output(
    value: Any,
    semantic_schema: dict[str, Any],
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return False, ["output is not an object"]
    if set(value) != {"semantic_flags"}:
        errors.append("output keys must be exactly ['semantic_flags']")
    flags = value.get("semantic_flags")
    allowed = set(
        semantic_schema["properties"]["semantic_flags"]["items"]["enum"]
    )
    if not isinstance(flags, list):
        errors.append("semantic_flags is not an array")
    else:
        if any(not isinstance(flag, str) for flag in flags):
            errors.append("semantic_flags contains non-string values")
        if len(flags) != len(set(flags)):
            errors.append("semantic_flags contains duplicates")
        unknown = {
            flag for flag in flags if isinstance(flag, str)
        } - allowed
        if unknown:
            errors.append(
                f"semantic_flags contains forbidden values: {sorted(unknown)}"
            )
    return not errors, errors


def merge_flags(
    structural_flags: list[str],
    semantic_flags: list[str],
    hybrid_policy: dict[str, Any],
) -> list[str]:
    structural_allowed = set(hybrid_policy["structural_flags"])
    semantic_allowed = set(hybrid_policy["semantic_flags"])
    if not set(structural_flags) <= structural_allowed:
        raise ValueError("structural layer contains forbidden flags")
    if not set(semantic_flags) <= semantic_allowed:
        raise ValueError("semantic layer contains forbidden flags")
    combined = set(structural_flags) | set(semantic_flags)
    return [
        flag
        for flag in hybrid_policy["flag_order"]
        if flag in combined
    ]


def derive_policy_decision(
    merged_flags: list[str],
    base_policy: dict[str, Any],
) -> dict[str, Any]:
    flag_set = set(merged_flags)
    for row in base_policy["priority"]:
        relevant = set(row["any_flags"])
        if (relevant and flag_set & relevant) or (
            not relevant and not flag_set
        ):
            return {
                "primary_status": row["primary_status"],
                "allowed_actions": row["allowed_actions"],
                "policy_expected_action": row[
                    "policy_expected_action"
                ],
            }
    raise ValueError(f"no readiness decision for flags: {merged_flags}")


def run_hybrid_gate(
    *,
    structured_state: dict[str, Any],
    contract: dict[str, Any],
    semantic_output: Any,
    base_policy: dict[str, Any] | None = None,
    hybrid_policy: dict[str, Any] | None = None,
    semantic_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_policy = base_policy or load_json(BASE_POLICY_PATH)
    hybrid_policy = hybrid_policy or load_json(HYBRID_POLICY_PATH)
    semantic_schema = semantic_schema or load_json(SEMANTIC_SCHEMA_PATH)
    valid, errors = validate_semantic_output(
        semantic_output,
        semantic_schema,
    )
    structural_flags = derive_structural_flags(
        structured_state,
        contract,
        hybrid_policy,
    )
    if not valid:
        return {
            "semantic_schema_valid": False,
            "semantic_schema_errors": errors,
            "structural_flags": structural_flags,
            "semantic_flags": None,
            "merged_flags": None,
            "primary_status": None,
            "allowed_actions": [],
            "policy_expected_action": None,
            "decision_status": "invalid_semantic_output",
        }
    semantic_flags = semantic_output["semantic_flags"]
    merged = merge_flags(
        structural_flags,
        semantic_flags,
        hybrid_policy,
    )
    decision = derive_policy_decision(merged, base_policy)
    return {
        "semantic_schema_valid": True,
        "semantic_schema_errors": [],
        "structural_flags": structural_flags,
        "semantic_flags": semantic_flags,
        "merged_flags": merged,
        **decision,
        "decision_status": "derived",
    }
