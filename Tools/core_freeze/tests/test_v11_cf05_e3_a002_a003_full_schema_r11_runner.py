from __future__ import annotations

import json
from pathlib import Path

from Tools.core_freeze.e3_routing import run_a002_a003_full_schema_r11 as module


WORKSPACE = Path(__file__).resolve().parents[3]
OPENING = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_full_schema_r11_opening_v1_20260811"


def test_opening_and_all_transport_corrected_payloads_validate():
    opening = module.validate_opening(OPENING)
    assert len(opening["cells"]) == 64
    assert len(opening["request_by_id"]) == 64
    assert all(payload["thinking"] == {"type": "disabled"} for payload in opening["request_by_id"].values())


def test_every_cell_is_new_and_bound_to_source_r1_cell():
    opening = module.validate_opening(OPENING)
    assert all(cell["cell_id"] != cell["source_r1_cell_id"] for cell in opening["cells"])
    assert len({cell["source_r1_cell_id"] for cell in opening["cells"]}) == 64


def test_parse_single_call_is_reused_without_tool_execution():
    parsed = module.parse_response({"choices": [{"message": {"content": None, "tool_calls": [{"function": {"name": "A002", "arguments": '{"formula":"FeS"}'}}]}}]})
    assert parsed["selected_tool_id"] == "A002"
    assert parsed["arguments"] == {"formula": "FeS"}


def test_payloads_contain_no_credentials_or_gold():
    opening = module.validate_opening(OPENING)
    for payload in opening["request_by_id"].values():
        text = json.dumps(payload, ensure_ascii=False).casefold()
        assert "api_key" not in text
        assert "primary_acceptable_tools" not in text
        assert payload["max_tokens"] == 256

