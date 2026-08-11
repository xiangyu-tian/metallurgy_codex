from __future__ import annotations

import json
from pathlib import Path

from Tools.core_freeze.e3_routing import build_a002_a003_full_schema_r1_opening as module


WORKSPACE = Path(__file__).resolve().parents[3]
OUTPUT = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_full_schema_r1_opening_v1_20260811"


def load(name: str):
    return json.loads((OUTPUT / name).read_text(encoding="utf-8"))


def test_opening_is_ready_but_unauthorized_and_no_call():
    report = load("a002_a003_full_schema_r1_opening_report.json")
    assert report["status"] == "execution_ready_but_external_api_unauthorized"
    assert report["external_api_calls"] == 0
    assert report["external_api_execution_authorized"] is False
    assert report["tool_execution_allowed"] is False


def test_grid_has_exactly_64_unique_cells():
    rows = load("a002_a003_full_schema_r1_run_cells.json")["cells"]
    assert len(rows) == 64
    assert len({row["cell_id"] for row in rows}) == 64
    assert {row["tool_pool_size"] for row in rows} == {17, 120}
    assert {row["pool_repeat"] for row in rows} == {"A", "B"}
    assert {row["pair_variant"] for row in rows} == {"element_stoichiometry", "molar_mass"}
    assert all(row["method"] == "full_schema" for row in rows)


def test_every_cell_has_one_hash_bound_payload():
    cells = load("a002_a003_full_schema_r1_run_cells.json")["cells"]
    requests = load("a002_a003_full_schema_r1_request_payloads.json")["requests"]
    request_by_id = {row["cell_id"]: row["payload"] for row in requests}
    assert len(request_by_id) == 64
    for cell in cells:
        assert module.canonical_hash(request_by_id[cell["cell_id"]]) == cell["payload_sha256"]


def test_payload_schema_count_matches_cell_size_and_never_executes_tools():
    cells = {row["cell_id"]: row for row in load("a002_a003_full_schema_r1_run_cells.json")["cells"]}
    for request in load("a002_a003_full_schema_r1_request_payloads.json")["requests"]:
        payload = request["payload"]
        assert len(payload["tools"]) == cells[request["cell_id"]]["tool_pool_size"]
        assert payload["tool_choice"] == "auto"
        assert "api_key" not in json.dumps(payload, ensure_ascii=False).casefold()


def test_router_payload_has_no_scoring_gold_or_endpoint_ids_in_prompt():
    prompt = load("a002_a003_full_schema_r1_prompt_snapshot.json")
    payloads = load("a002_a003_full_schema_r1_request_payloads.json")
    text = json.dumps(payloads, ensure_ascii=False)
    for field in prompt["gold_fields_forbidden"]:
        assert f'"{field}"' not in text
    assert "A002" not in prompt["system"]
    assert "A003" not in prompt["system"]


def test_opening_config_does_not_hardcode_endpoint_or_credentials():
    config = load("a002_a003_full_schema_r1_config_snapshot.json")
    text = json.dumps(config, ensure_ascii=False).casefold()
    assert "base_url" not in config
    assert "api_key" not in text
    assert "https://" not in text


def test_authorization_request_is_pending_and_exact():
    request = load("execution_authorization_request.json")
    assert request["decision"] == "pending_user_authorization"
    assert request["request_count"] == 64
    assert request["automatic_retry_allowed"] is False
    assert request["tool_execution_allowed"] is False


def test_manifest_hashes_all_six_opening_artifacts():
    manifest = load("artifact_manifest.json")
    assert manifest["artifact_count"] == 6
    assert {row["filename"] for row in manifest["artifacts"]} == {
        path.name for path in OUTPUT.iterdir() if path.name != "artifact_manifest.json"
    }
    for row in manifest["artifacts"]:
        assert module.common.file_hash(OUTPUT / row["filename"]) == row["sha256"]

