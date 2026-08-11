from __future__ import annotations

import json
from pathlib import Path

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common


WORKSPACE = Path(__file__).resolve().parents[3]
RESULTS = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_full_schema_r1_results_v1_20260811"
ANALYSIS = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_full_schema_r1_analysis_v1_20260811"


def load(directory: Path, name: str):
    return json.loads((directory / name).read_text(encoding="utf-8"))


def test_runtime_has_64_unique_one_attempt_results_without_tool_execution():
    rows = load(RESULTS, "a002_a003_full_schema_r1_results.json")["results"]
    assert len(rows) == 64
    assert len({row["cell_id"] for row in rows}) == 64
    assert len({row["response_id"] for row in rows}) == 64
    assert all(row["retry_count"] == 0 for row in rows)
    assert all(row["tool_executed"] is False for row in rows)


def test_runtime_transport_counts_are_exact():
    report = load(RESULTS, "a002_a003_full_schema_r1_runtime_report.json")
    assert report["transport_accepted_count"] == 64
    assert report["provider_error_count"] == 0
    assert report["exactly_one_tool_call_count"] == 59
    assert report["retries_executed"] == 0


def test_scored_rows_have_58_clean_primary_end_to_end_successes():
    rows = load(ANALYSIS, "a002_a003_full_schema_r1_scored_rows.json")["rows"]
    assert len(rows) == 64
    assert sum(row["primary_endpoint_hit"] for row in rows) == 59
    assert sum(row["arguments_exact"] for row in rows) == 58
    assert sum(row["primary_end_to_end"] for row in rows) == 58
    assert not any(row["alternative_hit"] for row in rows)


def test_17_tool_cells_are_perfect_and_all_failures_are_at_120():
    rows = load(ANALYSIS, "a002_a003_full_schema_r1_scored_rows.json")["rows"]
    seventeen = [row for row in rows if row["tool_pool_size"] == 17]
    failures = [row for row in rows if row["error_type"] != "none"]
    assert len(seventeen) == 32
    assert all(row["primary_end_to_end"] for row in seventeen)
    assert len(failures) == 6
    assert all(row["tool_pool_size"] == 120 for row in failures)


def test_failure_taxonomy_is_five_length_no_calls_and_one_truncated_arguments():
    report = load(ANALYSIS, "a002_a003_full_schema_r1_analysis_report.json")
    assert report["error_counts"] == {"invalid_arguments_json": 1, "no_single_tool_call_length": 5, "none": 58}
    assert report["reasoning_content_observed_count"] == 64
    assert report["transport_confound"]["detected"] is True


def test_scale_differences_match_frozen_rows():
    report = load(ANALYSIS, "a002_a003_full_schema_r1_analysis_report.json")
    assert report["scale_difference_120_minus_17"]["primary_endpoint_hit"] == -0.15625
    assert report["scale_difference_120_minus_17"]["primary_end_to_end"] == -0.1875
    assert report["confirmatory_inference_allowed"] is False


def test_result_and_analysis_manifests_are_valid():
    for directory in (RESULTS, ANALYSIS):
        manifest = load(directory, "artifact_manifest.json")
        for row in manifest["artifacts"]:
            assert common.file_hash(directory / row["filename"]) == row["sha256"]

