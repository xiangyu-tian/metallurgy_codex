from __future__ import annotations

import json
from pathlib import Path

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common
from Tools.core_freeze.e3_routing.build_a002_a003_full_schema_r1_opening import canonical_hash


WORKSPACE = Path(__file__).resolve().parents[3]
R1 = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_full_schema_r1_opening_v1_20260811"
R11 = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_full_schema_r11_opening_v1_20260811"


def load(directory: Path, name: str):
    return json.loads((directory / name).read_text(encoding="utf-8"))


def test_r11_is_ready_but_unauthorized_and_no_call():
    report = load(R11, "a002_a003_full_schema_r11_opening_report.json")
    assert report["status"] == "transport_corrected_execution_ready_but_unauthorized"
    assert report["external_api_calls"] == 0
    assert report["external_api_execution_authorized"] is False
    assert report["source_r1_responses_reused"] is False


def test_r11_has_exactly_64_new_unique_cells():
    cells = load(R11, "a002_a003_full_schema_r11_run_cells.json")["cells"]
    assert len(cells) == 64
    assert len({row["cell_id"] for row in cells}) == 64
    assert len({row["source_r1_cell_id"] for row in cells}) == 64
    assert all(row["execution_status"] == "not_executed_unauthorized" for row in cells)


def test_only_payload_change_is_explicit_thinking_disable():
    r1 = {row["cell_id"]: row["payload"] for row in load(R1, "a002_a003_full_schema_r1_request_payloads.json")["requests"]}
    r11 = load(R11, "a002_a003_full_schema_r11_request_payloads.json")["requests"]
    for row in r11:
        old = dict(r1[row["source_r1_cell_id"]])
        new = dict(row["payload"])
        assert "thinking" not in old
        assert new.pop("thinking") == {"type": "disabled"}
        assert new == old


def test_token_budget_and_all_other_request_material_are_unchanged():
    rows = load(R11, "a002_a003_full_schema_r11_single_axis_audit.json")["rows"]
    assert len(rows) == 64
    assert all(row["changed_top_level_keys"] == ["thinking"] for row in rows)
    assert all(row["source_max_tokens"] == row["r11_max_tokens"] == 256 for row in rows)
    assert all(row["single_axis_check_passed"] is True for row in rows)


def test_every_r11_payload_matches_its_frozen_hash():
    cells = {row["cell_id"]: row for row in load(R11, "a002_a003_full_schema_r11_run_cells.json")["cells"]}
    for request in load(R11, "a002_a003_full_schema_r11_request_payloads.json")["requests"]:
        assert canonical_hash(request["payload"]) == cells[request["cell_id"]]["payload_sha256"]


def test_no_credentials_or_gold_are_present():
    text = (R11 / "a002_a003_full_schema_r11_request_payloads.json").read_text(encoding="utf-8").casefold()
    assert "api_key" not in text
    assert "primary_acceptable_tools" not in text
    assert "scoring_rule" not in text
    assert "target_tool_id" not in text


def test_authorization_request_is_pending_and_exact():
    authorization = load(R11, "execution_authorization_request.json")
    assert authorization["decision"] == "pending_user_authorization"
    assert authorization["request_count"] == 64
    assert authorization["only_payload_change_from_r1"] == {"thinking": {"type": "disabled"}}
    assert authorization["max_tokens_unchanged"] == 256


def test_manifest_hashes_all_seven_pre_manifest_artifacts():
    manifest = load(R11, "artifact_manifest.json")
    assert manifest["artifact_count"] == 7
    assert {row["filename"] for row in manifest["artifacts"]} == {path.name for path in R11.iterdir() if path.name != "artifact_manifest.json"}
    for row in manifest["artifacts"]:
        assert common.file_hash(R11 / row["filename"]) == row["sha256"]

