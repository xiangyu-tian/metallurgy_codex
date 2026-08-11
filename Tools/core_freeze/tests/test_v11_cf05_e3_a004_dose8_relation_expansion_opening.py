from __future__ import annotations

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common
from Tools.core_freeze.e3_routing import build_e3_a004_dose8_relation_expansion_opening as module


def result():
    return module.build(common.load_json(module.CONFIG_PATH))


def test_opening_has_balanced_four_plus_four_candidate_capacity():
    screening = result()["screening"]
    assert screening["screened_candidate_count"] == 8
    assert screening["intended_relation_counts"] == {"functional_overlap": 4, "lexical": 4}
    assert screening["algorithmic_screen_pass_count"] == 8
    assert screening["relation_admission_count"] == 0


def test_existing_e3c024_is_reused_without_new_identity():
    row = result()["screening"]["rows"][0]
    assert row["candidate_id"] == "E3C024"
    assert row["candidate_origin"] == "existing_executable_cross_target_candidate"
    assert row["runtime_contract_already_passed"] is True
    assert row["target_specific_relation_review_complete"] is False
    assert row["eligible_for_relation_admission"] is False


def test_all_new_sources_remain_unimplemented_and_blocked():
    rows = result()["screening"]["rows"][1:]
    assert len(rows) == 7
    assert all(row["source_reference"].startswith("https://") for row in rows)
    assert all(row["runtime_contract_passed"] is False for row in rows)
    assert all(row["independence_review_passed"] is False for row in rows)
    assert all(row["eligible_for_relation_admission"] is False for row in rows)
    assert len(result()["blockers"]) == 8


def test_no_execution_or_formal_gate_is_opened():
    report = result()["report"]
    assert report["new_tool_identities_created"] == 0
    assert report["dependencies_installed"] == 0
    assert report["local_candidate_executions"] == 0
    assert report["external_api_calls"] == 0
    assert report["dose8_pools_generated"] == 0
    assert report["independent_validation_split_accessed"] is False
    assert report["formal_pool_generation_allowed"] is False
    assert report["confirmatory_inference_allowed"] is False
    assert report["cf05_status"] == "in_progress"
    assert report["core_frozen"] is False


def test_implementation_requires_separate_authorization():
    authorization = result()["authorization"]
    assert authorization["decision"] == "pending_user_authorization"
    assert authorization["authorized"] is False
    assert authorization["external_api_calls_requested"] == 0
    assert authorization["formal_pool_generation_requested"] is False
