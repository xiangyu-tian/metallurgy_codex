"""Validation helpers for the adopted E3 selector transport policy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common


POLICY_PATH = Path(__file__).with_name("e3_selector_transport_policy_v1.json")


def load_and_validate_policy() -> dict[str, Any]:
    policy = common.load_json(POLICY_PATH)
    if policy["decision"] != "adopted_for_future_e3_selector_runs":
        raise ValueError("E3 selector transport policy is not adopted")
    for binding in policy["evidence"].values():
        common.validate_binding(binding)
    requirements = policy["wire_payload_requirements"]
    if requirements["thinking"] != {"type": "disabled"}:
        raise ValueError("transport policy thinking setting changed")
    if requirements["selector_default_max_tokens"] != 256:
        raise ValueError("transport policy selector budget changed")
    if policy["external_api_calls_authorized_by_this_policy"] is not False:
        raise ValueError("transport policy cannot authorize API execution")
    return policy


def validate_selector_payload(payload: dict[str, Any], *, policy: dict[str, Any] | None = None) -> None:
    policy = policy or load_and_validate_policy()
    requirements = policy["wire_payload_requirements"]
    if "thinking" not in payload or payload["thinking"] != requirements["thinking"]:
        raise ValueError("selector payload must explicitly disable thinking")
    if payload.get("max_tokens") != requirements["selector_default_max_tokens"]:
        raise ValueError("selector payload max_tokens differs from frozen default")
    if payload.get("temperature") != requirements["temperature"]:
        raise ValueError("selector payload temperature differs from frozen policy")
    if payload.get("tool_choice") != requirements["tool_choice"]:
        raise ValueError("selector payload tool_choice differs from frozen policy")
    if not isinstance(payload.get("tools"), list) or not payload["tools"]:
        raise ValueError("selector payload must contain a non-empty native tool list")
    text = json.dumps(payload, ensure_ascii=False).casefold()
    if "api_key" in text or "authorization" in text:
        raise ValueError("selector payload contains credential material")


def audit_response(result: dict[str, Any], *, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_and_validate_policy()
    choices = ((result.get("raw_response") or {}).get("choices") or [{}])
    message = choices[0].get("message") or {}
    reasoning_observed = bool(message.get("reasoning_content")) or bool(
        (((result.get("usage") or {}).get("completion_tokens_details") or {}).get("reasoning_tokens", 0))
    )
    violation = reasoning_observed
    return {
        "reasoning_observed": reasoning_observed,
        "finish_reason": result.get("finish_reason"),
        "length_terminated": result.get("finish_reason") == "length",
        "transport_policy_violation": violation,
        "interpretation_allowed": not violation,
        "retry_allowed": policy["runtime_requirements"]["automatic_retry_allowed"],
    }
