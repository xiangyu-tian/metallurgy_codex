"""Synthetic analysis rows with no dependency on formal experiment data."""

from __future__ import annotations

from typing import Any


def record(
    *,
    task_id: str = "TASK-001",
    pool_repeat: str = "A",
    model_run_repeat: int = 1,
    method: str = "hierarchical",
    tool_pool_size: int = 120,
    pool_design: str = "controlled_dose",
    near_neighbor_type: str = "functional_overlap",
    near_neighbor_count: int = 8,
    correct: bool = True,
    request_status: str = "accepted",
    execution_status: str | None = "success",
) -> dict[str, Any]:
    condition = f"{pool_design}-{near_neighbor_type}-{near_neighbor_count}-{tool_pool_size}"
    selected_tool = "T-GOLD" if correct else "T-WRONG"
    end_to_end_correct: bool | None = correct
    if request_status == "not_accepted":
        selected_tool = None
        execution_status = None
        end_to_end_correct = None
    elif execution_status != "success":
        selected_tool = None
        end_to_end_correct = False
    return {
        "task_id": task_id,
        "minimal_pair_group": f"MPG-{task_id}",
        "target_tool_family": "FAMILY-THERMO",
        "acceptable_tools": ["T-GOLD"],
        "tool_pool_id": (
            f"POOL-{task_id}-{pool_repeat}-R{model_run_repeat}-{method}-{condition}"
        ),
        "pool_family_id": f"PF-{task_id}-{pool_repeat}",
        "pool_repeat": pool_repeat,
        "model_run_repeat": model_run_repeat,
        "method": method,
        "tool_pool_size": tool_pool_size,
        "pool_design": pool_design,
        "near_neighbor_type": near_neighbor_type,
        "near_neighbor_count": near_neighbor_count,
        "selected_tool": selected_tool,
        "end_to_end_correct": end_to_end_correct,
        "request_status": request_status,
        "execution_status": execution_status,
    }


def document(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0-rc1.1",
        "metadata": {
            "dataset_version": "synthetic-test",
            "protocol_version": "1.0-rc3.1",
            "generated_at": "2026-07-27T00:00:00+08:00",
        },
        "records": records,
    }


def h3_triplet(
    *,
    functional_correct: bool,
    lexical_correct: bool,
    none_correct: bool,
    task_id: str = "TASK-001",
    pool_repeat: str = "A",
    model_run_repeat: int = 1,
    method: str = "hierarchical",
) -> list[dict[str, Any]]:
    shared = {
        "task_id": task_id,
        "pool_repeat": pool_repeat,
        "model_run_repeat": model_run_repeat,
        "method": method,
        "tool_pool_size": 120,
        "pool_design": "controlled_dose",
    }
    return [
        record(
            **shared,
            near_neighbor_type="functional_overlap",
            near_neighbor_count=8,
            correct=functional_correct,
        ),
        record(
            **shared,
            near_neighbor_type="lexical",
            near_neighbor_count=8,
            correct=lexical_correct,
        ),
        record(
            **shared,
            near_neighbor_type="none",
            near_neighbor_count=0,
            correct=none_correct,
        ),
    ]


def h4_pair(
    *,
    method: str,
    correct_17: bool,
    correct_120: bool,
    task_id: str = "TASK-001",
    pool_repeat: str = "A",
    model_run_repeat: int = 1,
) -> list[dict[str, Any]]:
    shared = {
        "task_id": task_id,
        "pool_repeat": pool_repeat,
        "model_run_repeat": model_run_repeat,
        "method": method,
        "pool_design": "mixed_realistic",
        "near_neighbor_type": "mixed",
        "near_neighbor_count": 8,
    }
    return [
        record(**shared, tool_pool_size=17, correct=correct_17),
        record(**shared, tool_pool_size=120, correct=correct_120),
    ]
