from __future__ import annotations

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common
from Tools.core_freeze.e3_routing import build_cf05_development_decision_candidate as module


def result():
    return module.build(common.load_json(module.CONFIG_PATH))


def test_candidate_freezes_four_method_definitions_after_adoption():
    built = result()
    assert [row["method"] for row in built["method_manifest"]] == [
        "full_schema",
        "lexical_top5",
        "dense_top5",
        "hierarchical",
    ]
    assert all(
        row["candidate_freeze_action"] == "freeze_after_project_owner_adoption"
        for row in built["method_manifest"]
    )


def test_candidate_does_not_pass_cf05_or_open_validation():
    built = result()
    assert built["decision"]["decision_status"] == "candidate_pending_project_owner_adoption"
    assert built["decision"]["cf05_status"] == "in_progress"
    assert "independent validation access" in built["decision"]["not_authorized_by_this_candidate"]
    assert built["report"]["core_frozen"] is False


def test_residual_risks_preserve_the_real_blocker():
    built = result()
    blockers = [row for row in built["risks"] if row["blocks_cf05_overall_pass"]]
    assert [row["risk_id"] for row in blockers] == ["CF05-RISK-002"]
    assert built["report"]["cf05_overall_blocker_count"] == 1


def test_builder_is_offline_and_non_confirmatory():
    report = result()["report"]
    assert report["external_api_calls"] == 0
    assert report["independent_validation_split_accessed"] is False
    assert report["confirmatory_inference_allowed"] is False
