from __future__ import annotations

import json
from pathlib import Path

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common


WORKSPACE = Path(__file__).resolve().parents[3]
RESULTS = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_full_schema_r11_results_v1_20260811"
ANALYSIS = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_r1_r11_paired_analysis_v1_20260811"


def load(directory: Path, name: str):
    return json.loads((directory / name).read_text(encoding="utf-8"))


def test_r11_runtime_is_64_unique_new_responses_without_retries_or_tools():
    rows = load(RESULTS, "a002_a003_full_schema_r11_results.json")["results"]
    assert len(rows) == 64
    assert len({row["response_id"] for row in rows}) == 64
    assert all(row["source_r1_response_reused"] is False for row in rows)
    assert all(row["retry_count"] == 0 and row["tool_executed"] is False for row in rows)


def test_r11_transport_correction_eliminates_reasoning_and_truncation():
    report = load(RESULTS, "a002_a003_full_schema_r11_runtime_report.json")
    assert report["transport_accepted_count"] == 64
    assert report["exactly_one_tool_call_count"] == 64
    assert report["reasoning_content_observed_count"] == 0
    assert report["plain_text_or_non_single_call_count"] == 0


def test_r11_scores_all_64_cells_end_to_end():
    rows = load(ANALYSIS, "a002_a003_r11_scored_rows.json")["rows"]
    assert len(rows) == 64
    assert all(row["primary_endpoint_hit"] for row in rows)
    assert all(row["arguments_exact"] for row in rows)
    assert all(row["primary_end_to_end"] for row in rows)


def test_pairing_is_complete_and_all_six_r1_failures_recover():
    rows = load(ANALYSIS, "a002_a003_r1_r11_paired_rows.json")["rows"]
    assert len(rows) == 64
    assert len({row["source_r1_cell_id"] for row in rows}) == 64
    assert sum(row["r1_failure_recovered_end_to_end"] for row in rows) == 6
    assert all(row["r11_error_type"] == "none" for row in rows)


def test_120_tool_primary_endpoint_and_end_to_end_restore_to_one():
    rows = load(ANALYSIS, "a002_a003_r1_r11_paired_summary.json")["rows"]
    size120 = next(row for row in rows if row["group_type"] == "pool_size" and row["tool_pool_size"] == 120)
    assert size120["r1_primary_endpoint_hit_rate"] == 0.84375
    assert size120["r11_primary_endpoint_hit_rate"] == 1.0
    assert size120["r1_primary_end_to_end_rate"] == 0.8125
    assert size120["r11_primary_end_to_end_rate"] == 1.0
    assert size120["recovered_end_to_end_failure_count"] == 6


def test_17_tool_cells_remain_unchanged_at_one():
    rows = load(ANALYSIS, "a002_a003_r1_r11_paired_summary.json")["rows"]
    size17 = next(row for row in rows if row["group_type"] == "pool_size" and row["tool_pool_size"] == 17)
    assert size17["r1_primary_end_to_end_rate"] == 1.0
    assert size17["r11_primary_end_to_end_rate"] == 1.0
    assert size17["delta_primary_end_to_end_rate"] == 0.0


def test_report_keeps_development_and_core_freeze_boundaries():
    report = load(ANALYSIS, "a002_a003_r1_r11_paired_report.json")
    assert report["r1_end_to_end_failure_count"] == 6
    assert report["r11_end_to_end_failure_count"] == 0
    assert report["confirmatory_inference_allowed"] is False
    assert report["core_frozen"] is False


def test_result_and_analysis_manifests_are_valid():
    for directory in (RESULTS, ANALYSIS):
        manifest = load(directory, "artifact_manifest.json")
        for row in manifest["artifacts"]:
            assert common.file_hash(directory / row["filename"]) == row["sha256"]

