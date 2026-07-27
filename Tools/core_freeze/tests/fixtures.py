"""Synthetic analysis rows with no dependency on formal experiment data."""

from __future__ import annotations

import math
import random
from typing import Any

from Tools.core_freeze.analysis_core import H4_METHODS


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
    difficulty_score: int = 2,
    schema_token_count: int = 500,
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
        "difficulty_score": difficulty_score,
        "schema_token_count": schema_token_count,
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


def formal_glmm_document(
    *,
    task_count: int = 12,
    model_run_count: int = 3,
    seed: int = 20260727,
) -> dict[str, Any]:
    """Create a non-separable crossed-effects dataset for R engine tests."""

    rng = random.Random(seed)
    records: list[dict[str, Any]] = []
    method_effect = {
        "full_schema": -0.15,
        "lexical_top5": -0.25,
        "dense_top5": -0.05,
        "hierarchical": 0.15,
    }
    h3_condition_effect = {
        ("none", 0): 0.0,
        ("lexical", 4): -0.25,
        ("lexical", 8): -0.55,
        ("functional_overlap", 4): -0.65,
        ("functional_overlap", 8): -1.15,
    }
    h4_size_slope = {
        "full_schema": -0.75,
        "lexical_top5": -0.58,
        "dense_top5": -0.42,
        "hierarchical": -0.12,
    }

    def bernoulli(logit: float) -> bool:
        probability = 1 / (1 + math.exp(-logit))
        return rng.random() < probability

    for task_index in range(task_count):
        task_id = f"FORMAL-{task_index:03d}"
        difficulty_score = task_index % 6
        task_effect = (-0.8, -0.4, 0.0, 0.4, 0.8)[task_index % 5]
        target_family = f"FAMILY-{task_index % 4}"
        minimal_pair_group = f"MPG-{task_index // 2}"
        for pool_index, pool_repeat in enumerate(("A", "B", "C", "D", "E")):
            pool_effect = (-0.3, -0.15, 0.0, 0.15, 0.3)[pool_index]
            for model_run_repeat in range(1, model_run_count + 1):
                run_effect = (model_run_repeat - 2) * 0.12
                for method_index, method in enumerate(H4_METHODS):
                    for neighbor_type, neighbor_count in h3_condition_effect:
                        logit = (
                            1.4
                            + task_effect
                            + pool_effect
                            + run_effect
                            + method_effect[method]
                            + h3_condition_effect[(neighbor_type, neighbor_count)]
                        )
                        row = record(
                            task_id=task_id,
                            pool_repeat=pool_repeat,
                            model_run_repeat=model_run_repeat,
                            method=method,
                            tool_pool_size=120,
                            pool_design="controlled_dose",
                            near_neighbor_type=neighbor_type,
                            near_neighbor_count=neighbor_count,
                            correct=bernoulli(logit),
                            difficulty_score=difficulty_score,
                            schema_token_count=(
                                1250
                                + method_index * 35
                                + pool_index * 7
                                + neighbor_count * 3
                            ),
                        )
                        row["minimal_pair_group"] = minimal_pair_group
                        row["target_tool_family"] = target_family
                        records.append(row)

                    for tool_pool_size in (17, 50, 100, 120):
                        log_scale = math.log(tool_pool_size / 17)
                        logit = (
                            1.8
                            + task_effect
                            + pool_effect
                            + run_effect
                            + method_effect[method]
                            + h4_size_slope[method] * log_scale
                        )
                        row = record(
                            task_id=task_id,
                            pool_repeat=pool_repeat,
                            model_run_repeat=model_run_repeat,
                            method=method,
                            tool_pool_size=tool_pool_size,
                            pool_design="mixed_realistic",
                            near_neighbor_type="mixed",
                            near_neighbor_count=8,
                            correct=bernoulli(logit),
                            difficulty_score=difficulty_score,
                            schema_token_count=(
                                tool_pool_size * 11
                                + method_index * 35
                                + pool_index * 7
                            ),
                        )
                        row["minimal_pair_group"] = minimal_pair_group
                        row["target_tool_family"] = target_family
                        records.append(row)
    return document(records)
