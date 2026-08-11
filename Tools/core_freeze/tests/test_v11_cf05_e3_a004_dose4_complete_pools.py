from __future__ import annotations

from Tools.core_freeze.e3_routing import build_e3_a004_dose4_complete_pools as module
from Tools.core_freeze.e3_routing import build_e3_a004_hardcase_opening as old


def result():
    return module.build(old.load_json(module.CONFIG_PATH))


def test_dose4_grid_contains_four_sizes_five_repeats_three_conditions():
    manifest = result()["manifest"]
    assert manifest["pool_count"] == 60
    assert {
        (row["tool_pool_size"], row["pool_repeat"], row["near_neighbor_type"], row["near_neighbor_count"])
        for row in manifest["records"]
    } == {
        (size, repeat, neighbor_type, count)
        for size in [17, 50, 100, 120]
        for repeat in ["A", "B", "C", "D", "E"]
        for neighbor_type, count in [("none", 0), ("lexical", 4), ("functional_overlap", 4)]
    }


def test_all_pool_invariants_and_legacy_anchors_pass():
    built = result()
    assert built["audit"]["all_pool_invariants_passed"] is True
    assert built["audit"]["paired_dose4_neutral_bases_equal"] is True
    assert built["compatibility"]["all_six_legacy_anchors_preserved"] is True
    assert all(row["tool_order_exact_match"] for row in built["compatibility"]["rows"])


def test_functional_label_does_not_overclaim_expert_validation():
    relations = result()["relations"]
    assert relations["functional_overlap_operationalization"] == "contract_mismatch"
    assert relations["expert_validated_functional_overlap"] is False
    functional = [
        row for row in result()["manifest"]["records"]
        if row["near_neighbor_type"] == "functional_overlap"
    ]
    assert functional
    assert all(row["evidence_relation_type"] == "contract_mismatch" for row in functional)


def test_formal_gates_remain_closed():
    report = result()["report"]
    assert report["external_api_calls"] == 0
    assert report["tool_calls_executed"] == 0
    assert report["new_tool_identities_created"] == 0
    assert report["independent_validation_split_accessed"] is False
    assert report["confirmatory_inference_allowed"] is False
    assert report["formal_pool_generation_allowed"] is False
    assert report["cf05_status"] == "in_progress"
    assert report["core_frozen"] is False
