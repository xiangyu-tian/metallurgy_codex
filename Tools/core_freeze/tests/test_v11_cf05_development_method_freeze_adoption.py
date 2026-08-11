from __future__ import annotations

from datetime import datetime
from pathlib import Path

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common


WORKSPACE = Path(__file__).resolve().parents[3]
ADOPTION = WORKSPACE / "Tools/core_freeze/e3_routing/cf05_development_method_freeze_adoption_v1.json"


def test_adoption_is_bound_and_keeps_cf05_open():
    record = common.load_json(ADOPTION)
    assert record["decision"] == "adopted"
    assert record["adopted_scope"]["methods"] == [
        "full_schema",
        "lexical_top5",
        "dense_top5",
        "hierarchical",
    ]
    assert record["adopted_scope"]["stop_tuning_on_consumed_development_tasks"] is True
    assert record["adopted_scope"]["multiple_tool_calls_are_itt_errors"] is True
    assert record["cf05_status"] == "in_progress"
    assert record["core_frozen"] is False


def test_all_adoption_bindings_validate():
    record = common.load_json(ADOPTION)
    for binding in record["bindings"].values():
        common.validate_binding(binding)


def test_adoption_does_not_open_external_or_validation_work():
    record = common.load_json(ADOPTION)
    assert record["external_api_calls_authorized"] is False
    assert record["independent_validation_split_access_allowed"] is False
    assert record["confirmatory_inference_allowed"] is False
    assert datetime.fromisoformat(record["adopted_at"]).tzinfo is not None
