from __future__ import annotations

import json
from pathlib import Path

from Tools.core_freeze.e3_routing import run_a002_a003_full_schema_r1 as module


WORKSPACE = Path(__file__).resolve().parents[3]
OPENING = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_full_schema_r1_opening_v1_20260811"


def test_opening_manifest_and_all_payload_hashes_validate():
    opening = module.validate_opening(OPENING)
    assert len(opening["cells"]) == 64
    assert len(opening["request_by_id"]) == 64


def test_parse_exact_single_function_call():
    response = {
        "choices": [{
            "message": {
                "content": None,
                "tool_calls": [{"function": {"name": "A003", "arguments": '{"formula":"Fe2O3"}'}}],
            }
        }]
    }
    parsed = module.parse_response(response)
    assert parsed["exactly_one_tool_call"] is True
    assert parsed["selected_tool_id"] == "A003"
    assert parsed["arguments"] == {"formula": "Fe2O3"}


def test_parse_plain_text_is_not_selection():
    parsed = module.parse_response({"choices": [{"message": {"content": "159.687", "tool_calls": []}}]})
    assert parsed["exactly_one_tool_call"] is False
    assert parsed["selected_tool_id"] is None


def test_payloads_contain_no_credentials_and_are_one_call_policy():
    opening = module.validate_opening(OPENING)
    for payload in opening["request_by_id"].values():
        text = json.dumps(payload, ensure_ascii=False).casefold()
        assert "api_key" not in text
        assert payload["tool_choice"] == "auto"

