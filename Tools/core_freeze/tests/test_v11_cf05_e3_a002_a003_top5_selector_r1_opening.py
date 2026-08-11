from __future__ import annotations

import hashlib
import json
from pathlib import Path

from Tools.core_freeze.e3_routing.e3_transport_policy import validate_selector_payload


WORKSPACE = Path(__file__).resolve().parents[3]
OUTPUT = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_top5_selector_r1_opening_v1_20260811"
AUTHORIZATION = WORKSPACE / "Tools/core_freeze/e3_routing/a002_a003_top5_selector_r1_execution_authorization_v1.json"


def load(filename: str):
    return json.loads((OUTPUT / filename).read_text(encoding="utf-8"))


def canonical_hash(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def test_opening_is_complete_but_unauthorized():
    report = load("a002_a003_top5_selector_r1_opening_report.json")
    assert report["status"] == "execution_ready_but_external_api_unauthorized"
    assert report["scheduled_cell_count"] == 192
    assert report["method_cell_counts"] == {
        "lexical_top5": 64,
        "dense_top5": 64,
        "hierarchical": 64,
    }
    assert report["explicit_thinking_disabled_count"] == 192
    assert report["external_api_calls"] == 0
    assert report["tool_calls_executed"] == 0
    assert report["external_api_execution_authorized"] is False
    assert not AUTHORIZATION.exists()


def test_all_192_payloads_obey_transport_policy_and_expose_five_tools():
    requests = load("a002_a003_top5_selector_r1_request_payloads.json")["requests"]
    assert len(requests) == len({row["cell_id"] for row in requests}) == 192
    for row in requests:
        validate_selector_payload(row["payload"])
        assert len(row["payload"]["tools"]) == 5
        assert len({tool["function"]["name"] for tool in row["payload"]["tools"]}) == 5


def test_run_cells_bind_payload_hashes_and_remain_unexecuted():
    requests = {
        row["cell_id"]: row["payload"]
        for row in load("a002_a003_top5_selector_r1_request_payloads.json")["requests"]
    }
    cells = load("a002_a003_top5_selector_r1_run_cells.json")["cells"]
    assert len(cells) == 192
    assert [row["sequence"] for row in cells] == list(range(1, 193))
    for cell in cells:
        assert cell["payload_sha256"] == canonical_hash(requests[cell["cell_id"]])
        assert cell["visible_tool_count"] == 5
        assert cell["request_attempt_limit"] == 1
        assert cell["execution_status"] == "not_executed_unauthorized"


def test_router_visible_payloads_do_not_contain_gold_or_secrets():
    payload_text = json.dumps(
        load("a002_a003_top5_selector_r1_request_payloads.json"),
        ensure_ascii=False,
    ).casefold()
    for forbidden in (
        "primary_acceptable_tools",
        "alternative_success_tools",
        "family_hit_tools",
        "scientific_success_tools",
        "api_key",
    ):
        assert forbidden not in payload_text


def test_authorization_request_is_pending_and_non_executing():
    request = load("execution_authorization_request.json")
    assert request["decision"] == "pending_user_authorization"
    assert request["request_count"] == 192
    assert request["thinking"] == {"type": "disabled"}
    assert request["request_attempts_per_cell"] == 1
    assert request["automatic_retry_allowed"] is False
    assert request["tool_execution_allowed"] is False
    assert request["external_api_execution_authorized"] is False


def test_manifest_matches_all_opening_artifacts():
    manifest = load("artifact_manifest.json")
    rows = manifest["artifacts"]
    assert manifest["artifact_count"] == len(rows) == 6
    assert {row["filename"] for row in rows} == {
        path.name for path in OUTPUT.iterdir() if path.name != "artifact_manifest.json"
    }
    for row in rows:
        path = OUTPUT / row["filename"]
        assert path.stat().st_size == row["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
