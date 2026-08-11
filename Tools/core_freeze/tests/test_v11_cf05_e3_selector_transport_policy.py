from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from Tools.core_freeze.e3_routing import e3_transport_policy as module


WORKSPACE = Path(__file__).resolve().parents[3]
R11 = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_full_schema_r11_opening_v1_20260811/a002_a003_full_schema_r11_request_payloads.json"
RESULTS = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_full_schema_r11_results_v1_20260811/a002_a003_full_schema_r11_results.json"


def test_policy_is_adopted_but_does_not_authorize_api_calls():
    policy = module.load_and_validate_policy()
    assert policy["decision"] == "adopted_for_future_e3_selector_runs"
    assert policy["external_api_calls_authorized_by_this_policy"] is False
    assert policy["core_frozen"] is False


def test_all_r11_payloads_satisfy_transport_policy():
    rows = json.loads(R11.read_text(encoding="utf-8"))["requests"]
    assert len(rows) == 64
    for row in rows:
        module.validate_selector_payload(row["payload"])


def test_missing_or_enabled_thinking_is_rejected():
    payload = json.loads(R11.read_text(encoding="utf-8"))["requests"][0]["payload"]
    missing = copy.deepcopy(payload)
    missing.pop("thinking")
    with pytest.raises(ValueError, match="explicitly disable thinking"):
        module.validate_selector_payload(missing)
    enabled = copy.deepcopy(payload)
    enabled["thinking"] = {"type": "enabled"}
    with pytest.raises(ValueError, match="explicitly disable thinking"):
        module.validate_selector_payload(enabled)


def test_post_hoc_budget_change_is_rejected():
    payload = copy.deepcopy(json.loads(R11.read_text(encoding="utf-8"))["requests"][0]["payload"])
    payload["max_tokens"] = 512
    with pytest.raises(ValueError, match="max_tokens"):
        module.validate_selector_payload(payload)


def test_all_r11_responses_pass_response_transport_audit():
    results = json.loads(RESULTS.read_text(encoding="utf-8"))["results"]
    audits = [module.audit_response(row) for row in results]
    assert len(audits) == 64
    assert not any(row["transport_policy_violation"] for row in audits)
    assert not any(row["length_terminated"] for row in audits)
    assert all(row["retry_allowed"] is False for row in audits)

