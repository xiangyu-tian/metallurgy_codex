from __future__ import annotations

import json
from pathlib import Path

from Tools.core_freeze.e3_routing import build_a002_a003_pool_views as module


WORKSPACE = Path(__file__).resolve().parents[3]
OUTPUT = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_pool_views_v1_20260811"


def load(name: str):
    return json.loads((OUTPUT / name).read_text(encoding="utf-8"))


def test_report_freezes_four_views_without_external_calls():
    report = load("a002_a003_pool_view_report.json")
    assert report["view_count"] == 4
    assert report["selected_pool_sizes"] == [17, 120]
    assert report["external_api_calls"] == 0
    assert report["confirmatory_use_allowed"] is False


def test_views_have_exact_sizes_unique_tools_and_both_endpoints():
    for view in load("a002_a003_selected_pool_views.json")["views"]:
        assert len(view["tool_order"]) == view["tool_pool_size"]
        assert len(set(view["tool_order"])) == view["tool_pool_size"]
        assert {"A002", "A003"}.issubset(view["tool_order"])
        assert [row["function"]["name"] for row in view["openai_tools"]] == view["tool_order"]


def test_router_tasks_contain_no_gold_or_reference_fields():
    allowed = {"task_id", "pair_id", "pair_variant", "problem_text", "canonical_inputs"}
    tasks = load("a002_a003_router_visible_tasks.json")["tasks"]
    assert len(tasks) == 16
    assert all(set(task) == allowed for task in tasks)


def test_signature_screen_is_exhaustive_for_selected_views():
    rows = load("a002_a003_signature_compatibility_screen.json")["rows"]
    assert {row["tool_id"] for row in rows} == {"A002", "A003", "E3C002", "E3C018"}
    assert all(row["required_input_keys"] == ["formula"] for row in rows)


def test_candidate_execution_is_single_pass_per_task_candidate():
    rows = load("a002_a003_direct_candidate_execution_results.json")["rows"]
    assert len(rows) == 32
    assert len({(row["task_id"], row["candidate_tool_id"]) for row in rows}) == 32


def test_e3c002_is_acceptable_only_for_eight_element_tasks():
    rows = load("a002_a003_direct_candidate_execution_results.json")["rows"]
    accepted = [row for row in rows if row["candidate_tool_id"] == "E3C002" and row["directly_satisfies_frozen_scoring_rule"]]
    assert len(accepted) == 8
    assert all(row["task_id"].endswith("-ELEMENTS") for row in accepted)


def test_e3c018_never_satisfies_the_frozen_tasks():
    rows = load("a002_a003_direct_candidate_execution_results.json")["rows"]
    isotope_rows = [row for row in rows if row["candidate_tool_id"] == "E3C018"]
    assert len(isotope_rows) == 16
    assert not any(row["directly_satisfies_frozen_scoring_rule"] for row in isotope_rows)


def test_pool_specific_primary_and_alternative_sets_are_asymmetric():
    rows = load("a002_a003_pool_specific_scoring_registry.json")["rows"]
    assert len(rows) == 64
    for row in rows:
        if row["task_id"].endswith("-ELEMENTS"):
            expected = ["A002", "E3C002"] if row["tool_pool_size"] == 120 else ["A002"]
            assert row["primary_acceptable_tools"] == expected
            assert row["alternative_success_tools"] == []
        else:
            assert row["primary_acceptable_tools"] == ["A003"]
            assert row["alternative_success_tools"] == ["A002"]


def test_scoring_rows_do_not_claim_full_catalog_gold():
    rows = load("a002_a003_pool_specific_scoring_registry.json")["rows"]
    assert all(row["pool_specific_acceptable_set_revalidated"] is True for row in rows)
    assert all(row["full_catalog_acceptable_set_frozen"] is False for row in rows)


def test_manifest_hashes_all_preceding_artifacts():
    manifest = load("artifact_manifest.json")
    assert manifest["artifact_count"] == 7
    assert {row["filename"] for row in manifest["artifacts"]} == {
        path.name for path in OUTPUT.iterdir() if path.name != "artifact_manifest.json"
    }
    for row in manifest["artifacts"]:
        assert module.common.file_hash(OUTPUT / row["filename"]) == row["sha256"]

