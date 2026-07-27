"""Problem-group cluster bootstrap for already paired and pool-averaged rows."""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

try:
    from .analysis_core import load_json, write_json
    from .build_paired_contrasts import overall_effect
except ImportError:  # pragma: no cover - supports direct script execution
    from analysis_core import load_json, write_json
    from build_paired_contrasts import overall_effect


def percentile(values: Iterable[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("percentile requires at least one value")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def cluster_bootstrap(
    rows: Iterable[dict[str, Any]],
    effect_field: str,
    *,
    n_resamples: int = 2000,
    seed: int = 20260727,
) -> dict[str, Any]:
    rows = list(rows)
    if not rows:
        raise ValueError("cluster bootstrap requires at least one row")
    if n_resamples < 1:
        raise ValueError("n_resamples must be >= 1")

    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        clusters[row["bootstrap_cluster_id"]].append(row)
    cluster_ids = sorted(clusters)
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(n_resamples):
        sampled_rows: list[dict[str, Any]] = []
        for _ in cluster_ids:
            cluster_id = rng.choice(cluster_ids)
            sampled_rows.extend(clusters[cluster_id])
        samples.append(overall_effect(sampled_rows, effect_field))

    return {
        "effect_field": effect_field,
        "estimate": overall_effect(rows, effect_field),
        "cluster_count": len(cluster_ids),
        "n_resamples": n_resamples,
        "seed": seed,
        "confidence_interval": {
            "level": 0.95,
            "lower": percentile(samples, 0.025),
            "upper": percentile(samples, 0.975),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--effect-field", required=True)
    parser.add_argument("--n-resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260727)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = load_json(args.input)
    result = cluster_bootstrap(
        rows,
        args.effect_field,
        n_resamples=args.n_resamples,
        seed=args.seed,
    )
    write_json(args.output, result)
    print(json.dumps({"output": str(args.output.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
