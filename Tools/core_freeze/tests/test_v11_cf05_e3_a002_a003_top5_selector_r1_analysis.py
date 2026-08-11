from __future__ import annotations

import hashlib
import json
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[3]
OUTPUT = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_top5_selector_r1_analysis_v1_20260811"


def load(filename: str):
    return json.loads((OUTPUT / filename).read_text(encoding="utf-8"))


def test_intention_to_treat_report_preserves_all_terminal_failures():
    report = load("a002_a003_top5_selector_r1_analysis_report.json")
    assert report["result_count"] == 192
    assert report["denominator_policy"] == "intention_to_treat_all_192_scheduled_cells"
    assert report["overall"]["transport_accepted"] == 0.994792
    assert report["overall"]["exactly_one_tool_call"] == 0.979167
    assert report["overall"]["primary_end_to_end"] == 0.979167
    assert report["error_counts"] == {
        "multiple_tool_calls": 3,
        "none": 188,
        "provider_error_terminal": 1,
    }
    assert report["all_single_calls_primary_correct"] is True
    assert report["primary_endpoint_hit_rate_given_single_call"] == 1.0


def test_method_and_scale_results_are_fixed():
    report = load("a002_a003_top5_selector_r1_analysis_report.json")
    assert report["method_primary_end_to_end"] == {
        "dense_top5": 1.0,
        "hierarchical": 0.96875,
        "lexical_top5": 0.96875,
    }
    assert report["scale_difference_120_minus_17"]["primary_end_to_end"] == -0.041667
    assert report["reasoning_content_observed_count"] == 0


def test_scored_rows_keep_failures_and_do_not_execute_tools():
    rows = load("a002_a003_top5_selector_r1_scored_rows.json")["rows"]
    assert len(rows) == len({row["cell_id"] for row in rows}) == 192
    failures = [row for row in rows if not row["primary_end_to_end"]]
    assert len(failures) == 4
    assert {row["task_id"] for row in failures} == {"E3-MP-CU_NH3_4_SO4-ELEMENTS"}
    assert {row["tool_pool_size"] for row in failures} == {120}
    assert {row["method"] for row in failures} == {"lexical_top5", "hierarchical"}


def test_analysis_is_offline_and_nonconfirmatory():
    report = load("a002_a003_top5_selector_r1_analysis_report.json")
    assert report["external_api_calls_in_analysis"] == 0
    assert report["external_api_calls_in_source_run"] == 192
    assert report["tool_calls_executed"] == 0
    assert report["retries_executed"] == 0
    assert report["independent_validation_split_accessed"] is False
    assert report["confirmatory_inference_allowed"] is False
    assert report["core_frozen"] is False


def test_manifest_hashes_every_analysis_artifact():
    manifest = load("artifact_manifest.json")
    assert manifest["artifact_count"] == len(manifest["artifacts"]) == 6
    for row in manifest["artifacts"]:
        path = OUTPUT / row["filename"]
        assert path.is_file()
        assert path.stat().st_size == row["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
