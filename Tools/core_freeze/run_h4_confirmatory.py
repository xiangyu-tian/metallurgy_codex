"""Run the H4 minimum confirmatory data-contract and paired-effect analysis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .analysis_core import H4_METHODS, load_json, require_valid_document, write_json
    from .bootstrap_clusters import cluster_bootstrap
    from .build_paired_contrasts import (
        aggregate_pool_repeats,
        build_h4_method_contrasts,
        build_h4_scale_pairs,
        exact_sign_test,
        holm_adjust,
        overall_effect,
        run_repeat_summary,
        task_effects,
    )
except ImportError:  # pragma: no cover - supports direct script execution
    from analysis_core import H4_METHODS, load_json, require_valid_document, write_json
    from bootstrap_clusters import cluster_bootstrap
    from build_paired_contrasts import (
        aggregate_pool_repeats,
        build_h4_method_contrasts,
        build_h4_scale_pairs,
        exact_sign_test,
        holm_adjust,
        overall_effect,
        run_repeat_summary,
        task_effects,
    )


def _require_complete(rows: list[dict[str, Any]], allow_incomplete: bool) -> None:
    incomplete = [
        (
            row["task_id"],
            row["model_run_repeat"],
            row.get("method", row.get("baseline_method")),
            row["pool_repeats"],
        )
        for row in rows
        if not row["pool_repeats_complete"]
    ]
    if incomplete and not allow_incomplete:
        raise ValueError(f"H4 requires A-E pool repeats; incomplete cells: {incomplete}")


def run_h4(
    document: dict[str, Any],
    *,
    n_resamples: int = 2000,
    seed: int = 20260727,
    allow_incomplete: bool = False,
) -> dict[str, Any]:
    records = require_valid_document(document)
    scale = build_h4_scale_pairs(records)
    if scale["duplicate_cells"]:
        raise ValueError(f"H4 duplicate condition cells: {scale['duplicate_cells']}")
    if not scale["scale_contrasts"]:
        raise ValueError("H4 has no complete mixed_realistic 120 vs 17 pairs")

    scale_results: dict[str, Any] = {}
    for method in H4_METHODS:
        raw_rows = [
            row for row in scale["scale_contrasts"] if row["method"] == method
        ]
        if not raw_rows:
            raise ValueError(f"H4 is missing registered method: {method}")
        rows = aggregate_pool_repeats(
            raw_rows,
            "d_h4",
            extra_group_fields=("method",),
        )
        _require_complete(rows, allow_incomplete)
        scale_results[method] = {
            "estimate": overall_effect(rows, "d_h4"),
            "run_repeat_summary": run_repeat_summary(rows, "d_h4"),
            "cluster_bootstrap": cluster_bootstrap(
                rows,
                "d_h4",
                n_resamples=n_resamples,
                seed=seed,
            ),
        }

    planned = build_h4_method_contrasts(scale["scale_contrasts"])
    if not planned["method_contrasts"]:
        raise ValueError("H4 has no complete hierarchical-vs-baseline method pairs")

    comparison_results: dict[str, Any] = {}
    raw_p_values: dict[str, float] = {}
    for index, baseline in enumerate(H4_METHODS[1:]):
        raw_rows = [
            row
            for row in planned["method_contrasts"]
            if row["baseline_method"] == baseline
        ]
        if not raw_rows:
            raise ValueError(f"H4 is missing planned comparison: {baseline}")
        rows = aggregate_pool_repeats(
            raw_rows,
            "h4_method_difference",
            extra_group_fields=("baseline_method",),
        )
        _require_complete(rows, allow_incomplete)
        name = f"hierarchical_vs_{baseline}"
        raw_p_values[name] = exact_sign_test(
            task_effects(rows, "h4_method_difference"),
            alternative="greater",
        )
        comparison_results[name] = {
            "estimate": overall_effect(rows, "h4_method_difference"),
            "cluster_bootstrap": cluster_bootstrap(
                rows,
                "h4_method_difference",
                n_resamples=n_resamples,
                seed=seed + index,
            ),
        }

    adjusted = holm_adjust(raw_p_values)
    for name, result in comparison_results.items():
        result["one_sided_p_value"] = raw_p_values[name]
        result["holm_adjusted_p_value"] = adjusted[name]

    paired_validation_support = all(
        result["estimate"] > 0 and result["holm_adjusted_p_value"] < 0.05
        for result in comparison_results.values()
    )
    return {
        "report_version": "1.0-rc1.1",
        "hypothesis": "H4",
        "analysis_scope": {
            "pool_design": "mixed_realistic",
            "endpoint_contrast": "Accuracy120 - Accuracy17",
            "planned_method_comparisons": list(comparison_results),
            "multiplicity_control": "Holm",
        },
        "method_scale_effects": scale_results,
        "planned_comparisons": comparison_results,
        "paired_validation_support": paired_validation_support,
        "formal_mixed_effect_model": {
            "status": "not_run",
            "required_model": "H4 mixed_realistic GLMM with method*log(tool_pool_size)",
        },
        "missingness": {
            "scale_pairs": scale["missing_pairs"],
            "method_pairs": planned["missing_pairs"],
            "ignored_record_count": scale["ignored_record_count"],
        },
        "cf11_status": "in_progress",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--n-resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260727)
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_h4(
        load_json(args.input),
        n_resamples=args.n_resamples,
        seed=args.seed,
        allow_incomplete=args.allow_incomplete,
    )
    write_json(args.output, result)
    print(json.dumps({"output": str(args.output.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
