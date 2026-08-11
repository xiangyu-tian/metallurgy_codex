from __future__ import annotations

import hashlib
import json
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[3]
V1 = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_top5_views_v1_20260811"
AUDIT = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_dense_repro_audit_v1_20260811"
DEVELOPMENT = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_dense_query_development_v1_20260811"
V2 = WORKSPACE / "outputs/v11_cf05_e3_a002_a003_top5_views_v2_20260811"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v1_failure_is_preserved_as_negative_development_evidence():
    report = load(V1 / "a002_a003_top5_views_report.json")
    assert report["status"] == "top5_views_built_recall_gate_failed"
    dense = next(row for row in report["method_summary"] if row["method"] == "dense_top5")
    assert dense["primary_acceptable_recall_at_5_count"] == 62
    rows = load(V1 / "a002_a003_top5_retrieval_results.json")["rows"]
    failures = [
        (row["task_id"], row["source_pool_view_id"])
        for row in rows
        if row["method"] == "dense_top5" and not row["primary_acceptable_recall_at_5"]
    ]
    assert failures == [
        ("E3-MP-FE2O3-ELEMENTS", "A002-A003-120-A-LEXICAL8-V1"),
        ("E3-MP-FE2O3-ELEMENTS", "A002-A003-120-B-LEXICAL8-V1"),
    ]


def test_dense_cross_process_reproducibility_is_exact():
    audit = load(AUDIT / "dense_cross_process_reproducibility_audit.json")
    assert audit["process_count"] == 3
    assert audit["all_process_results_exactly_equal"] is True
    assert audit["fresh_index_exactly_equals_frozen_index"] is True
    assert audit["fresh_and_frozen_rankings_exactly_equal"] is True
    assert audit["external_api_calls"] == 0
    signatures = {row["result_signature_sha256"] for row in audit["runs"]}
    assert len(signatures) == 1
    for run in audit["runs"]:
        result = run["result"]
        assert result["query_vector_sha256"] == "a11e5fea8caa9abad323390479f74a0b6f1b669ac4bcc303468fc278e0840190"
        for ranking in result["rankings"].values():
            assert ranking["fresh"] == ranking["frozen"]
            assert next(index for index, row in enumerate(ranking["fresh"], 1) if row["tool_id"] == "A002") == 7


def test_predeclared_dense_query_selection_promotes_v2():
    summary = load(DEVELOPMENT / "dense_query_candidate_summary.json")
    assert summary["selected_candidate_id"] == "dense_v2_direct_output_tool"
    assert summary["selected_by_predeclared_rule"] is True
    assert summary["selected_candidate_passes_64_of_64_recall_gate"] is True
    rows = {row["candidate_id"]: row for row in summary["candidate_summaries"]}
    assert rows["dense_v1_article_retrieval"]["primary_acceptable_recall_at_5_count"] == 62
    assert rows["dense_v2_direct_output_tool"]["primary_acceptable_recall_at_5_count"] == 64
    assert rows["dense_v2_direct_output_tool"]["mean_reciprocal_rank_of_nearest_primary_acceptable_tool"] > rows["dense_v1_article_retrieval"]["mean_reciprocal_rank_of_nearest_primary_acceptable_tool"]
    assert summary["gold_visible_to_retriever"] is False
    assert summary["independent_validation_split_accessed"] is False
    assert summary["external_api_calls"] == 0


def test_v2_top5_grid_is_complete_and_all_recall_gates_pass():
    report = load(V2 / "a002_a003_top5_views_report.json")
    assert report["status"] == "top5_views_built_development_opening_eligible"
    assert report["retrieval_cell_count"] == 192
    assert report["schema_view_count"] == 192
    assert report["all_cells_primary_acceptable_recall_at_5"] is True
    assert report["external_api_calls"] == 0
    rows = load(V2 / "a002_a003_top5_retrieval_results.json")["rows"]
    assert len(rows) == len({row["retrieval_id"] for row in rows}) == 192
    assert all(row["primary_acceptable_recall_at_5"] for row in rows)
    assert {method: sum(row["method"] == method for row in rows) for method in {row["method"] for row in rows}} == {
        "lexical_top5": 64,
        "dense_top5": 64,
        "hierarchical": 64,
    }


def test_v2_schema_views_are_exact_top5_subsets():
    views = load(V2 / "a002_a003_top5_schema_views.json")["views"]
    results = {
        row["retrieval_id"]: row
        for row in load(V2 / "a002_a003_top5_retrieval_results.json")["rows"]
    }
    assert len(views) == 192
    for view in views:
        ids = view["ordered_tool_ids"]
        assert len(ids) == len(set(ids)) == 5
        assert ids == results[view["schema_view_id"]]["selected_tool_ids"]
        assert [tool["function"]["name"] for tool in view["tools"]]


def test_v2_dense_policy_changes_query_instruction_only():
    policy = load(V2 / "dense_query_policy_snapshot.json")
    assert policy["instruction_prefix"] == "为这个问题检索能够直接产生所请求输出的专业计算工具："
    for field in (
        "changes_embedding_model",
        "changes_document_renderer",
        "changes_frozen_index",
        "changes_similarity_or_tie_break",
        "external_api_calls_authorized",
        "independent_validation_split_access_allowed",
        "confirmatory_inference_allowed",
        "core_frozen",
    ):
        assert policy[field] is False


def test_generated_manifests_match_artifacts():
    for directory in (V1, AUDIT, DEVELOPMENT, V2):
        manifest = load(directory / "artifact_manifest.json")
        rows = manifest["artifacts"]
        if "artifact_count" in manifest:
            assert manifest["artifact_count"] == len(rows)
        assert len({row["filename"] for row in rows}) == len(rows)
        for row in rows:
            path = directory / row["filename"]
            assert path.is_file()
            assert path.stat().st_size == row["bytes"]
            assert sha256(path) == row["sha256"]
