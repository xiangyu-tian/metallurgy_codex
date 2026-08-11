from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from Tools.core_freeze.e3_routing.e3_transport_policy import validate_selector_payload


WORKSPACE = Path(__file__).resolve().parents[3]
OUTPUT = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_top5_selector_r2_r3_opening_v1_20260811"
R1 = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_top5_selector_r1_opening_v1_20260811"


def load(directory: Path, filename: str):
    return json.loads((directory / filename).read_text(encoding="utf-8"))


def test_opening_contains_two_complete_new_repeats_and_no_api_calls():
    report = load(OUTPUT, "a002_a003_top5_selector_r2_r3_opening_report.json")
    assert report["status"] == "complete_repeats_execution_ready_but_external_api_unauthorized"
    assert report["scheduled_cell_count"] == 384
    assert report["repeat_cell_counts"] == {"R2": 192, "R3": 192}
    assert report["failed_r1_cells_only"] is False
    assert report["external_api_calls"] == 0
    assert report["external_api_execution_authorized"] is False


def test_every_r1_cell_has_exactly_one_r2_and_one_r3_cell():
    cells = load(OUTPUT, "a002_a003_top5_selector_r2_r3_run_cells.json")["cells"]
    assert len(cells) == len({row["cell_id"] for row in cells}) == 384
    counts = Counter(row["source_r1_cell_id"] for row in cells)
    repeats = {}
    for row in cells:
        repeats.setdefault(row["source_r1_cell_id"], set()).add(row["model_run_repeat"])
    assert set(counts.values()) == {2}
    assert all(value == {"R2", "R3"} for value in repeats.values())


def test_all_repeat_payloads_are_byte_semantically_equal_to_r1():
    r1 = {
        row["cell_id"]: row["payload"]
        for row in load(R1, "a002_a003_top5_selector_r1_request_payloads.json")["requests"]
    }
    requests = load(OUTPUT, "a002_a003_top5_selector_r2_r3_request_payloads.json")["requests"]
    assert len(requests) == 384
    for row in requests:
        assert row["payload"] == r1[row["source_r1_cell_id"]]
        validate_selector_payload(row["payload"])


def test_single_axis_audit_passes_for_all_384_cells():
    rows = load(OUTPUT, "a002_a003_top5_selector_r2_r3_single_axis_audit.json")["rows"]
    assert len(rows) == 384
    assert all(row["payload_exactly_equal_to_r1"] for row in rows)
    assert all(row["task_schema_prompt_and_transport_unchanged"] for row in rows)
    assert all(row["new_request_required"] for row in rows)
    assert not any(row["source_r1_response_reuse_allowed"] for row in rows)


def test_authorization_request_is_pending_and_complete_not_selective():
    request = load(OUTPUT, "execution_authorization_request.json")
    assert request["decision"] == "pending_user_authorization"
    assert request["request_count"] == 384
    assert request["complete_repeat_counts"] == {"R2": 192, "R3": 192}
    assert request["failed_r1_cells_only"] is False
    assert request["payloads_identical_to_r1"] is True
    assert request["external_api_execution_authorized"] is False


def test_manifest_hashes_all_seven_opening_artifacts():
    manifest = load(OUTPUT, "artifact_manifest.json")
    assert manifest["artifact_count"] == len(manifest["artifacts"]) == 7
    for row in manifest["artifacts"]:
        path = OUTPUT / row["filename"]
        assert path.is_file()
        assert path.stat().st_size == row["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
