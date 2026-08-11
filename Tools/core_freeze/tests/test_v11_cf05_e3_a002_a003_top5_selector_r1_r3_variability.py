from __future__ import annotations

from collections import Counter

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common
from Tools.core_freeze.e3_routing import analyze_a002_a003_top5_selector_r1_r3_variability as module


def result():
    return module.build(common.load_json(module.CONFIG_PATH))


def test_all_three_repeats_are_scored_with_itt_denominator():
    built = result()
    assert len(built["rows"]) == 576
    assert Counter(row["model_run_repeat"] for row in built["rows"]) == Counter(
        {"R1": 192, "R2": 192, "R3": 192}
    )


def test_matched_units_have_exactly_three_repeats():
    built = result()
    assert len(built["unit_rows"]) == 192
    assert all(
        row["stable_correct"] + row["stable_failure"] + row["variable_correctness"] == 1
        for row in built["unit_rows"]
    )


def test_pairwise_tables_cover_all_matched_units():
    built = result()
    assert len(built["pairwise"]) == 3
    for row in built["pairwise"]:
        assert row["n"] == 192
        assert (
            row["both_correct_count"]
            + row["left_only_correct_count"]
            + row["right_only_correct_count"]
            + row["both_incorrect_count"]
            == 192
        )


def test_analysis_is_non_confirmatory_and_uses_no_new_calls():
    report = result()["report"]
    assert report["external_api_calls_in_source_runs"] == 576
    assert report["external_api_calls_in_analysis"] == 0
    assert report["retries_executed"] == 0
    assert report["confirmatory_inference_allowed"] is False
    assert report["core_frozen"] is False
