from __future__ import annotations

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common
from Tools.core_freeze.e3_routing import audit_cf05_five_target_pool_coverage as module


CONFIG_PATH = module.CONFIG_PATH.with_name("cf05_five_target_pool_coverage_audit_config_v1_1.json")


def result():
    return module.build(common.load_json(CONFIG_PATH))


def test_updated_audit_counts_completed_a004_dose4_grid():
    built = result()
    report = built["report"]
    assert report["strict_grid_complete_target_ids"] == ["A003"]
    assert report["existing_controlled_pool_record_count"] == 160
    assert report["required_strict_pool_record_count"] == 500
    assert report["missing_strict_pool_record_count"] == 340
    rows = {row["target_tool_id"]: row for row in built["rows"]}
    assert rows["A004"]["existing_controlled_pool_record_count"] == 60
    assert rows["A004"]["missing_strict_pool_record_count"] == 40


def test_neighbor_gaps_are_unchanged_by_pool_replication():
    report = result()["report"]
    assert report["neighbor_slot_gap_to_paired_4"] == 15
    assert report["neighbor_slot_gap_to_paired_8"] == 47
    assert report["new_tool_identities_created"] == 0


def test_a004_next_gate_is_dose8_relation_evidence():
    queue = result()["expansion_queue"]
    assert queue[0]["target_tool_id"] == "A004"
    assert queue[0]["immediate_goal"] == "add four lexical and four functional neighbors for dose 8"
    assert "completed dose-4 grid" in queue[0]["required_action"]


def test_updated_audit_keeps_formal_gates_closed():
    report = result()["report"]
    assert report["external_api_calls"] == 0
    assert report["independent_validation_split_accessed"] is False
    assert report["confirmatory_inference_allowed"] is False
    assert report["cf05_status"] == "in_progress"
    assert report["core_frozen"] is False
