"""Build the frozen H3 and H4 paired contrasts from validated raw rows."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

try:
    from .analysis_core import (
        H4_METHODS,
        POOL_REPEATS,
        bootstrap_cluster_id,
        load_json,
        require_valid_document,
        selection_correct,
        write_json,
    )
except ImportError:  # pragma: no cover - supports direct script execution
    from analysis_core import (
        H4_METHODS,
        POOL_REPEATS,
        bootstrap_cluster_id,
        load_json,
        require_valid_document,
        selection_correct,
        write_json,
    )


def _base_key(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        record["task_id"],
        record["pool_family_id"],
        record["pool_repeat"],
        record["model_run_repeat"],
        record["method"],
    )


def _base_fields(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": record["task_id"],
        "minimal_pair_group": record["minimal_pair_group"],
        "bootstrap_cluster_id": bootstrap_cluster_id(record),
        "target_tool_family": record["target_tool_family"],
        "pool_family_id": record["pool_family_id"],
        "pool_repeat": record["pool_repeat"],
        "model_run_repeat": record["model_run_repeat"],
        "method": record["method"],
    }


def _index_unique(
    records: Iterable[dict[str, Any]],
    condition,
) -> tuple[dict[tuple[Any, ...], dict[str, Any]], list[dict[str, Any]]]:
    index: dict[tuple[Any, ...], dict[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []
    for record in records:
        if not condition(record):
            continue
        key = _base_key(record)
        if key in index:
            duplicates.append({"key": list(key), "reason": "duplicate_condition_cell"})
        else:
            index[key] = record
    return index, duplicates


def build_h3_pairs(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    records = list(records)

    def is_h3(record: dict[str, Any]) -> bool:
        return (
            record["pool_design"] == "controlled_dose"
            and record["tool_pool_size"] == 120
            and (
                (
                    record["near_neighbor_type"]
                    in {"functional_overlap", "lexical"}
                    and record["near_neighbor_count"] == 8
                )
                or (
                    record["near_neighbor_type"] == "none"
                    and record["near_neighbor_count"] == 0
                )
            )
        )

    h3_records = [record for record in records if is_h3(record)]
    indexes: dict[str, dict[tuple[Any, ...], dict[str, Any]]] = {}
    duplicate_cells: list[dict[str, Any]] = []
    for neighbor_type, count in (
        ("functional_overlap", 8),
        ("lexical", 8),
        ("none", 0),
    ):
        index, duplicates = _index_unique(
            h3_records,
            lambda row, nt=neighbor_type, nc=count: (
                row["near_neighbor_type"] == nt
                and row["near_neighbor_count"] == nc
            ),
        )
        indexes[neighbor_type] = index
        duplicate_cells.extend(duplicates)

    candidate_keys = sorted(
        set(indexes["functional_overlap"]) | set(indexes["lexical"])
    )
    direct: list[dict[str, Any]] = []
    baselines: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for key in candidate_keys:
        functional = indexes["functional_overlap"].get(key)
        lexical = indexes["lexical"].get(key)
        if functional is None or lexical is None:
            missing.append(
                {
                    "key": list(key),
                    "contrast": "functional_overlap_8_vs_lexical_8",
                    "missing": [
                        name
                        for name, row in (
                            ("functional_overlap_8", functional),
                            ("lexical_8", lexical),
                        )
                        if row is None
                    ],
                }
            )
            continue

        functional_correct = selection_correct(functional)
        lexical_correct = selection_correct(lexical)
        if functional_correct is None or lexical_correct is None:
            missing.append(
                {
                    "key": list(key),
                    "contrast": "functional_overlap_8_vs_lexical_8",
                    "missing": ["observable_selection_result"],
                }
            )
            continue

        row = _base_fields(functional)
        row.update(
            {
                "functional_overlap_correct": functional_correct,
                "lexical_correct": lexical_correct,
                "d_h3": functional_correct - lexical_correct,
            }
        )
        direct.append(row)

        none_record = indexes["none"].get(key)
        none_correct = selection_correct(none_record) if none_record else None
        if none_correct is None:
            missing.append(
                {
                    "key": list(key),
                    "contrast": "h3_none_0_baseline",
                    "missing": ["none_0_or_observable_selection_result"],
                }
            )
            continue
        baselines.append(
            {
                **_base_fields(functional),
                "none_correct": none_correct,
                "effect_functional": functional_correct - none_correct,
                "effect_lexical": lexical_correct - none_correct,
            }
        )

    return {
        "hypothesis": "H3",
        "direct_contrasts": direct,
        "baseline_contrasts": baselines,
        "missing_pairs": missing,
        "duplicate_cells": duplicate_cells,
        "ignored_record_count": len(records) - len(h3_records),
    }


def build_h4_scale_pairs(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    records = list(records)
    h4_records = [
        record
        for record in records
        if record["pool_design"] == "mixed_realistic"
        and record["tool_pool_size"] in {17, 120}
    ]
    indexes: dict[int, dict[tuple[Any, ...], dict[str, Any]]] = {}
    duplicate_cells: list[dict[str, Any]] = []
    for size in (17, 120):
        index, duplicates = _index_unique(
            h4_records,
            lambda row, expected=size: row["tool_pool_size"] == expected,
        )
        indexes[size] = index
        duplicate_cells.extend(duplicates)

    candidate_keys = sorted(set(indexes[17]) | set(indexes[120]))
    contrasts: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for key in candidate_keys:
        small = indexes[17].get(key)
        large = indexes[120].get(key)
        if small is None or large is None:
            missing.append(
                {
                    "key": list(key),
                    "contrast": "mixed_realistic_120_vs_17",
                    "missing": [
                        str(size)
                        for size, row in ((17, small), (120, large))
                        if row is None
                    ],
                }
            )
            continue

        correct_17 = selection_correct(small)
        correct_120 = selection_correct(large)
        if correct_17 is None or correct_120 is None:
            missing.append(
                {
                    "key": list(key),
                    "contrast": "mixed_realistic_120_vs_17",
                    "missing": ["observable_selection_result"],
                }
            )
            continue
        contrasts.append(
            {
                **_base_fields(large),
                "correct_17": correct_17,
                "correct_120": correct_120,
                "d_h4": correct_120 - correct_17,
            }
        )

    return {
        "hypothesis": "H4",
        "scale_contrasts": contrasts,
        "missing_pairs": missing,
        "duplicate_cells": duplicate_cells,
        "ignored_record_count": len(records) - len(h4_records),
    }


def build_h4_method_contrasts(
    scale_contrasts: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    by_unit: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in scale_contrasts:
        key = (
            row["task_id"],
            row["pool_family_id"],
            row["pool_repeat"],
            row["model_run_repeat"],
        )
        method = row["method"]
        if method in by_unit[key]:
            raise ValueError(f"duplicate H4 method contrast for {key} / {method}")
        by_unit[key][method] = row

    contrasts: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    baselines = H4_METHODS[1:]
    for key, methods in sorted(by_unit.items()):
        hierarchical = methods.get("hierarchical")
        if hierarchical is None:
            missing.append(
                {
                    "key": list(key),
                    "contrast": "hierarchical_vs_baselines",
                    "missing": ["hierarchical"],
                }
            )
            continue
        for baseline in baselines:
            baseline_row = methods.get(baseline)
            if baseline_row is None:
                missing.append(
                    {
                        "key": list(key),
                        "contrast": f"hierarchical_vs_{baseline}",
                        "missing": [baseline],
                    }
                )
                continue
            contrasts.append(
                {
                    **{
                        field: hierarchical[field]
                        for field in (
                            "task_id",
                            "minimal_pair_group",
                            "bootstrap_cluster_id",
                            "target_tool_family",
                            "pool_family_id",
                            "pool_repeat",
                            "model_run_repeat",
                        )
                    },
                    "baseline_method": baseline,
                    "hierarchical_d_h4": hierarchical["d_h4"],
                    "baseline_d_h4": baseline_row["d_h4"],
                    "h4_method_difference": (
                        hierarchical["d_h4"] - baseline_row["d_h4"]
                    ),
                }
            )

    return {"method_contrasts": contrasts, "missing_pairs": missing}


def aggregate_pool_repeats(
    rows: Iterable[dict[str, Any]],
    effect_field: str,
    *,
    extra_group_fields: Iterable[str] = (),
) -> list[dict[str, Any]]:
    extra_group_fields = tuple(extra_group_fields)
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            row["task_id"],
            row["model_run_repeat"],
            *(row[field] for field in extra_group_fields),
        )
        groups[key].append(row)

    aggregated: list[dict[str, Any]] = []
    for _, group_rows in sorted(groups.items()):
        first = group_rows[0]
        repeats = sorted({row["pool_repeat"] for row in group_rows})
        values = [float(row[effect_field]) for row in group_rows]
        aggregated.append(
            {
                "task_id": first["task_id"],
                "minimal_pair_group": first["minimal_pair_group"],
                "bootstrap_cluster_id": first["bootstrap_cluster_id"],
                "target_tool_family": first["target_tool_family"],
                "model_run_repeat": first["model_run_repeat"],
                **{field: first[field] for field in extra_group_fields},
                effect_field: math.fsum(values) / len(values),
                "pool_repeats": repeats,
                "pool_repeat_count": len(repeats),
                "pool_repeats_complete": tuple(repeats) == POOL_REPEATS,
            }
        )
    return aggregated


def run_repeat_summary(
    rows: Iterable[dict[str, Any]],
    effect_field: str,
) -> list[dict[str, Any]]:
    by_repeat: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        by_repeat[row["model_run_repeat"]].append(float(row[effect_field]))
    return [
        {
            "model_run_repeat": repeat,
            "task_count": len(values),
            "mean_effect": math.fsum(values) / len(values),
        }
        for repeat, values in sorted(by_repeat.items())
    ]


def overall_effect(rows: Iterable[dict[str, Any]], effect_field: str) -> float:
    summaries = run_repeat_summary(rows, effect_field)
    if not summaries:
        raise ValueError("cannot estimate an effect from zero rows")
    return math.fsum(row["mean_effect"] for row in summaries) / len(summaries)


def task_effects(rows: Iterable[dict[str, Any]], effect_field: str) -> list[float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[row["task_id"]].append(float(row[effect_field]))
    return [
        math.fsum(values) / len(values)
        for _, values in sorted(grouped.items())
    ]


def exact_sign_test(values: Iterable[float], *, alternative: str) -> float:
    nonzero = [value for value in values if value != 0]
    n = len(nonzero)
    if n == 0:
        return 1.0
    positives = sum(value > 0 for value in nonzero)
    if alternative == "greater":
        tail = range(positives, n + 1)
    elif alternative == "less":
        tail = range(0, positives + 1)
    else:
        raise ValueError("alternative must be 'greater' or 'less'")
    return sum(math.comb(n, k) for k in tail) / (2**n)


def holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    adjusted: dict[str, float] = {}
    running_max = 0.0
    family_size = len(ordered)
    for rank, (name, p_value) in enumerate(ordered):
        candidate = min(1.0, (family_size - rank) * p_value)
        running_max = max(running_max, candidate)
        adjusted[name] = running_max
    return adjusted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--hypothesis", choices=("h3", "h4"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = require_valid_document(load_json(args.input))
    if args.hypothesis == "h3":
        result = build_h3_pairs(records)
    else:
        result = build_h4_scale_pairs(records)
        result.update(build_h4_method_contrasts(result["scale_contrasts"]))
    write_json(args.output, result)
    print(json.dumps({"output": str(args.output.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
