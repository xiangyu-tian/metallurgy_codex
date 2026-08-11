from __future__ import annotations

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common
from Tools.core_freeze.e3_routing import audit_cf05_five_target_pool_coverage as module


def result():
    return module.build(common.load_json(module.CONFIG_PATH))


def test_a003_is_the_only_complete_strict_grid():
    built = result()
    report = built["report"]
    assert report["strict_grid_complete_target_ids"] == ["A003"]
    assert report["strict_grid_complete_target_count"] == 1
    assert report["existing_controlled_pool_record_count"] == 106
    assert report["required_strict_pool_record_count"] == 500
    assert report["missing_strict_pool_record_count"] == 394


def test_effective_neighbor_coverage_is_recomputed_from_latest_evidence():
    rows = {row["target_tool_id"]: row for row in result()["rows"]}
    assert rows["A003"]["effective_lexical_neighbor_count"] == 8
    assert rows["A003"]["effective_functional_neighbor_count"] == 8
    assert rows["A004"]["effective_lexical_neighbor_count"] == 4
    assert rows["A004"]["effective_functional_neighbor_count"] == 4
    assert rows["A004"]["existing_controlled_pool_record_count"] == 6


def test_real_relation_gaps_are_not_filled_with_invented_neighbors():
    built = result()
    assert built["report"]["neighbor_slot_gap_to_paired_4"] == 15
    assert built["report"]["neighbor_slot_gap_to_paired_8"] == 47
    assert built["report"]["new_tool_identities_created"] == 0
    assert [row["target_tool_id"] for row in built["expansion_queue"]] == [
        "A004",
        "B019",
        "A002",
        "A001",
    ]


def test_audit_keeps_all_formal_gates_closed():
    report = result()["report"]
    assert report["external_api_calls"] == 0
    assert report["independent_validation_split_accessed"] is False
    assert report["confirmatory_inference_allowed"] is False
    assert report["cf05_status"] == "in_progress"
    assert report["core_frozen"] is False
