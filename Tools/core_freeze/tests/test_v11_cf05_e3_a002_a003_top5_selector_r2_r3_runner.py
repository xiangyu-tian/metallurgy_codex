from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from Tools.core_freeze.e3_routing import run_a002_a003_top5_selector_r2_r3 as module


WORKSPACE = Path(__file__).resolve().parents[3]
OPENING = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_top5_selector_r2_r3_opening_v1_20260811"


def authorization_for(opening):
    return {
        "opening_id": module.EXPECTED_OPENING_ID,
        "decision": module.EXPECTED_DECISION,
        "provider": "deepseek",
        "model": opening["config"]["model"],
        "scheduled_request_count": 384,
        "opening_manifest_sha256": module.common.file_hash(opening["paths"]["manifest"]),
        "request_payloads_sha256": module.common.file_hash(opening["paths"]["requests"]),
        "runner_sha256": module.common.file_hash(Path(module.__file__)),
        "external_data_sharing_authorized": True,
        "external_api_execution_authorized": True,
        "tool_execution_authorized": False,
        "provider_retry_authorized": False,
        "independent_validation_split_access_authorized": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
        "authorized_at": datetime.now(timezone.utc).isoformat(),
        "authorized_scope": {
            "task_text_count": 16,
            "schema_view_count": 192,
            "request_count": 384,
            "complete_repeat_counts": {"R2": 192, "R3": 192},
            "visible_tools_per_request": 5,
            "explicit_thinking": {"type": "disabled"},
            "max_tokens": 256,
            "request_attempts_per_cell": 1,
        },
    }


def test_opening_and_all_384_payloads_validate():
    opening = module.validate_opening(OPENING)
    assert len(opening["cells"]) == 384
    assert len(opening["request_by_id"]) == 384
    assert sum(row["model_run_repeat"] == "R2" for row in opening["cells"]) == 192
    assert sum(row["model_run_repeat"] == "R3" for row in opening["cells"]) == 192


def test_authorization_is_exactly_bound_to_opening_and_runner():
    opening = module.validate_opening(OPENING)
    authorization = authorization_for(opening)
    module.validate_authorization(authorization, opening)
    changed = copy.deepcopy(authorization)
    changed["authorized_scope"]["complete_repeat_counts"]["R3"] = 191
    with pytest.raises(ValueError, match="scope changed"):
        module.validate_authorization(changed, opening)


def test_payloads_contain_no_credentials_or_gold():
    opening = module.validate_opening(OPENING)
    for payload in opening["request_by_id"].values():
        text = json.dumps(payload, ensure_ascii=False).casefold()
        assert "api_key" not in text
        assert "primary_acceptable_tools" not in text
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["max_tokens"] == 256


def test_execution_order_is_complete_r2_then_complete_r3():
    cells = module.validate_opening(OPENING)["cells"]
    assert [row["model_run_repeat"] for row in cells[:192]] == ["R2"] * 192
    assert [row["model_run_repeat"] for row in cells[192:]] == ["R3"] * 192
