"""Run the H3 minimum confirmatory data-contract and paired-effect analysis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .analysis_core import load_json, require_valid_document, write_json
    from .bootstrap_clusters import cluster_bootstrap
    from .build_paired_contrasts import (
        aggregate_pool_repeats,
        build_h3_pairs,
        exact_sign_test,
        overall_effect,
        run_repeat_summary,
        task_effects,
    )
except ImportError:  # pragma: no cover - supports direct script execution
    from analysis_core import load_json, require_valid_document, write_json
    from bootstrap_clusters import cluster_bootstrap
    from build_paired_contrasts import (
        aggregate_pool_repeats,
        build_h3_pairs,
        exact_sign_test,
        overall_effect,
        run_repeat_summary,
        task_effects,
    )


def _require_complete(rows: list[dict[str, Any]], allow_incomplete: bool) -> None:
    incomplete = [
        (row["task_id"], row["model_run_repeat"], row["pool_repeats"])
        for row in rows
        if not row["pool_repeats_complete"]
    ]
    if incomplete and not allow_incomplete:
        raise ValueError(f"H3 requires A-E pool repeats; incomplete cells: {incomplete}")


def run_h3(
    document: dict[str, Any],
    *,
    n_resamples: int = 2000,
    seed: int = 20260727,
    allow_incomplete: bool = False,
) -> dict[str, Any]:
    records = require_valid_document(document)
    pairs = build_h3_pairs(records)
    if pairs["duplicate_cells"]:
        raise ValueError(f"H3 duplicate condition cells: {pairs['duplicate_cells']}")
    if not pairs["direct_contrasts"]:
        raise ValueError("H3 has no complete functional_overlap-8 vs lexical-8 pairs")

    direct = aggregate_pool_repeats(pairs["direct_contrasts"], "d_h3")
    _require_complete(direct, allow_incomplete)
    baseline_functional = aggregate_pool_repeats(
        pairs["baseline_contrasts"],
        "effect_functional",
    )
    baseline_lexical = aggregate_pool_repeats(
        pairs["baseline_contrasts"],
        "effect_lexical",
    )

    bootstrap = cluster_bootstrap(
        direct,
        "d_h3",
        n_resamples=n_resamples,
        seed=seed,
    )
    supporting_p = exact_sign_test(
        task_effects(direct, "d_h3"),
        alternative="less",
    )
    return {
        "report_version": "1.0-rc1.1",
        "hypothesis": "H3",
        "analysis_scope": {
            "pool_design": "controlled_dose",
            "tool_pool_size": 120,
            "near_neighbor_count": 8,
            "direct_contrast": "functional_overlap - lexical",
        },
        "descriptive_effect": {
            "estimate": overall_effect(direct, "d_h3"),
            "run_repeat_summary": run_repeat_summary(direct, "d_h3"),
            "cluster_bootstrap": bootstrap,
        },
        "auxiliary_baselines": {
            "functional_overlap_minus_none": (
                overall_effect(baseline_functional, "effect_functional")
                if baseline_functional
                else None
            ),
            "lexical_minus_none": (
                overall_effect(baseline_lexical, "effect_lexical")
                if baseline_lexical
                else None
            ),
        },
        "supporting_paired_sign_test": {
            "alternative": "less",
            "p_value": supporting_p,
            "note": "Minimum-package diagnostic; not the frozen mixed-effect model.",
        },
        "formal_mixed_effect_model": {
            "status": "not_run",
            "required_model": "H3 controlled_dose GLMM with model_run_repeat random intercept",
        },
        "missingness": {
            "missing_pairs": pairs["missing_pairs"],
            "ignored_record_count": pairs["ignored_record_count"],
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
    result = run_h3(
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
