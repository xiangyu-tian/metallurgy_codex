"""Prepare the v1.1 CF-08 clustered power and repeat-count candidate.

This is a planning analysis, not a confirmatory hypothesis test. It uses the
independent base-task group as the sampling unit and keeps the proposed
minimum meaningful effect and repeat count pending project approval.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import NormalDist, mean, median, stdev
from typing import Any


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
CF03_DIR = PROJECT_ROOT / "outputs" / "v11_cf03_candidate_20260731"
POWER_INPUT_PATH = CF03_DIR / "power_input.json"
CF03_MANIFEST_PATH = CF03_DIR / "artifact_manifest.json"
BENEFIT_RECORDS_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "e1b_v2_benefit_r3_20260730"
    / "run_records.jsonl"
)
GROUP_EFFECTS_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "e1b_v2_benefit_analysis_r3_20260730"
    / "group_effects.csv"
)
BENEFIT_REPORT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "e1b_v2_benefit_analysis_r3_20260730"
    / "benefit_analysis_report.json"
)

ALPHA_ONE_SIDED = 0.05
POWER_TARGETS = (0.80, 0.90)
EFFECT_GRID = (0.05, 0.08, 0.10)
PILOT_UNCERTAINTY_INFLATION = 0.15
TOOL_FAMILY_COUNT = 5
TASKS_PER_GROUP_CANDIDATE = 2
CONDITION_COUNT = 2
REPEAT_COUNT_CANDIDATE = 3


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def round_up_multiple(value: float, multiple: int) -> int:
    return int(math.ceil(value / multiple) * multiple)


def load_group_effects() -> list[dict[str, Any]]:
    with GROUP_EFFECTS_PATH.open(encoding="utf-8", newline="") as stream:
        return [
            {
                "base_task_group_id": row["base_task_group_id"],
                "task_count": int(row["task_count"]),
                "paired_cell_count": int(row["paired_cell_count"]),
                "accuracy_gain": float(row["accuracy_gain"]),
            }
            for row in csv.DictReader(stream)
        ]


def paired_differences() -> dict[str, list[int]]:
    records = load_jsonl(BENEFIT_RECORDS_PATH)
    cells: dict[tuple[str, int], dict[str, int]] = defaultdict(dict)
    for row in records:
        cells[(row["task_id"], int(row["model_run_repeat"]))][
            row["condition"]
        ] = int(row["correct"])
    values: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for (task_id, repeat), conditions in cells.items():
        difference = (
            conditions["forced_verified_oracle_parameters"]
            - conditions["no_tool"]
        )
        values[task_id].append((repeat, difference))
    return {
        task_id: [
            difference
            for _, difference in sorted(rows, key=lambda item: item[0])
        ]
        for task_id, rows in values.items()
    }


def repeat_stability() -> dict[str, Any]:
    task_values = paired_differences()
    repeat_count = len(next(iter(task_values.values())))
    task_count = len(task_values)
    task_means = [mean(values) for values in task_values.values()]
    grand_mean = mean(task_means)
    ms_between = (
        repeat_count
        * sum((value - grand_mean) ** 2 for value in task_means)
        / (task_count - 1)
    )
    within_sum_squares = sum(
        sum((value - mean(values)) ** 2 for value in values)
        for values in task_values.values()
    )
    ms_within = within_sum_squares / (
        task_count * (repeat_count - 1)
    )
    denominator = ms_between + (repeat_count - 1) * ms_within
    icc = (
        (ms_between - ms_within) / denominator
        if denominator
        else 1.0
    )
    by_repeat = []
    for repeat_index in range(repeat_count):
        values = [rows[repeat_index] for rows in task_values.values()]
        by_repeat.append(
            {
                "model_run_repeat": repeat_index + 1,
                "task_count": task_count,
                "positive_count": sum(value > 0 for value in values),
                "zero_count": sum(value == 0 for value in values),
                "negative_count": sum(value < 0 for value in values),
                "accuracy_gain": mean(values),
            }
        )
    patterns = Counter(tuple(values) for values in task_values.values())
    stable_count = sum(
        count for pattern, count in patterns.items() if len(set(pattern)) == 1
    )
    return {
        "task_count": task_count,
        "pilot_repeat_count": repeat_count,
        "stable_task_count": stable_count,
        "unstable_task_count": task_count - stable_count,
        "stable_task_fraction": stable_count / task_count,
        "repeat_level_accuracy_gains": by_repeat,
        "repeat_gain_range": (
            max(row["accuracy_gain"] for row in by_repeat)
            - min(row["accuracy_gain"] for row in by_repeat)
        ),
        "one_way_random_effects_icc": icc,
        "icc_method": "balanced one-way random-effects ANOVA on paired differences",
        "task_repeat_patterns": [
            {"pattern": list(pattern), "task_count": count}
            for pattern, count in sorted(patterns.items())
        ],
    }


def planning_power(
    effect: float,
    group_sd: float,
    group_count: int,
    alpha: float = ALPHA_ONE_SIDED,
) -> float:
    z_alpha = NormalDist().inv_cdf(1.0 - alpha)
    noncentrality = effect * math.sqrt(group_count) / group_sd
    return NormalDist().cdf(noncentrality - z_alpha)


def required_group_count(
    effect: float,
    group_sd: float,
    target_power: float,
    alpha: float = ALPHA_ONE_SIDED,
) -> int:
    z_alpha = NormalDist().inv_cdf(1.0 - alpha)
    z_power = NormalDist().inv_cdf(target_power)
    raw = ((z_alpha + z_power) * group_sd / effect) ** 2
    return int(math.ceil(raw))


def build_sample_size_options(group_sd: float) -> list[dict[str, Any]]:
    options = []
    for effect in EFFECT_GRID:
        for target_power in POWER_TARGETS:
            base_groups = required_group_count(
                effect,
                group_sd,
                target_power,
            )
            inflated_groups = round_up_multiple(
                base_groups * (1.0 + PILOT_UNCERTAINTY_INFLATION),
                TOOL_FAMILY_COUNT,
            )
            task_count = inflated_groups * TASKS_PER_GROUP_CANDIDATE
            model_cells = (
                task_count
                * CONDITION_COUNT
                * REPEAT_COUNT_CANDIDATE
            )
            options.append(
                {
                    "minimum_meaningful_accuracy_gain": effect,
                    "target_power": target_power,
                    "alpha_one_sided": ALPHA_ONE_SIDED,
                    "required_base_task_groups_uninflated": base_groups,
                    "pilot_uncertainty_inflation": (
                        PILOT_UNCERTAINTY_INFLATION
                    ),
                    "recommended_base_task_groups": inflated_groups,
                    "base_task_groups_per_tool_family_if_balanced": (
                        inflated_groups // TOOL_FAMILY_COUNT
                    ),
                    "tasks_per_base_task_group": (
                        TASKS_PER_GROUP_CANDIDATE
                    ),
                    "planned_task_count": task_count,
                    "model_run_repeats": REPEAT_COUNT_CANDIDATE,
                    "condition_count": CONDITION_COUNT,
                    "planned_model_cells": model_cells,
                }
            )
    return options


def build_candidate(
    group_sd: float,
    benefit_report: dict[str, Any],
) -> dict[str, Any]:
    target_effect = 0.05
    target_power = 0.80
    base_groups = required_group_count(
        target_effect,
        group_sd,
        target_power,
    )
    candidate_groups = round_up_multiple(
        base_groups * (1.0 + PILOT_UNCERTAINTY_INFLATION),
        TOOL_FAMILY_COUNT,
    )
    tasks = candidate_groups * TASKS_PER_GROUP_CANDIDATE
    paired_repeats = tasks * REPEAT_COUNT_CANDIDATE
    model_cells = paired_repeats * CONDITION_COUNT
    costs = benefit_report["condition_costs"]
    pilot_pair_count = benefit_report["paired_cell_count"]
    tokens_per_paired_repeat = (
        costs["no_tool"]["usage_totals"]["total_tokens"]
        + costs["forced_verified_oracle_parameters"]["usage_totals"][
            "total_tokens"
        ]
    ) / pilot_pair_count
    mean_cell_latency_ms = mean(
        [
            costs["no_tool"]["mean_latency_ms"],
            costs["forced_verified_oracle_parameters"]["mean_latency_ms"],
        ]
    )
    return {
        "candidate_id": "E1B-FORMAL-DESIGN-CANDIDATE-V1",
        "approval_status": "pending",
        "minimum_meaningful_accuracy_gain": target_effect,
        "minimum_meaningful_effect_status": "proposed_not_frozen",
        "alpha": ALPHA_ONE_SIDED,
        "test_direction": "one_sided_positive_gain",
        "target_power": target_power,
        "pilot_group_standard_deviation": group_sd,
        "base_task_groups_uninflated": base_groups,
        "pilot_uncertainty_inflation": PILOT_UNCERTAINTY_INFLATION,
        "base_task_groups": candidate_groups,
        "base_task_groups_per_verified_tool_family": (
            candidate_groups // TOOL_FAMILY_COUNT
        ),
        "tasks_per_base_task_group": TASKS_PER_GROUP_CANDIDATE,
        "task_count": tasks,
        "condition_count": CONDITION_COUNT,
        "model_run_repeats": REPEAT_COUNT_CANDIDATE,
        "paired_repeat_count": paired_repeats,
        "model_cell_count": model_cells,
        "approximate_power_at_candidate_size": planning_power(
            target_effect,
            group_sd,
            candidate_groups,
        ),
        "projected_total_tokens_from_pilot_mean": (
            tokens_per_paired_repeat * paired_repeats
        ),
        "projected_sequential_latency_minutes_from_pilot_mean": (
            mean_cell_latency_ms * model_cells / 60_000
        ),
        "formal_repeat_count_frozen": False,
        "formal_sample_size_frozen": False,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_analysis(output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    power_input = load_json(POWER_INPUT_PATH)
    benefit_report = load_json(BENEFIT_REPORT_PATH)
    group_rows = load_group_effects()
    group_values = [row["accuracy_gain"] for row in group_rows]
    group_sd = stdev(group_values)
    stability = repeat_stability()
    options = build_sample_size_options(group_sd)
    candidate = build_candidate(group_sd, benefit_report)

    checks = [
        {
            "check_id": "CF08-INDEPENDENT-UNIT",
            "passed": power_input["analysis_constraints"][
                "cluster_unit"
            ]
            == "base_task_group_id"
            and power_input["analysis_constraints"][
                "independence_unit_is_not_paired_repeat"
            ]
            is True,
            "evidence": "base_task_group_id is the planning unit",
        },
        {
            "check_id": "CF08-PILOT-GROUPS",
            "passed": len(group_values)
            == power_input["benefit_calibration"][
                "base_task_group_count"
            ],
            "evidence": f"base_task_group_count={len(group_values)}",
        },
        {
            "check_id": "CF08-REPEAT-STABILITY",
            "passed": stability["stable_task_fraction"] >= 0.90
            and stability["repeat_gain_range"] <= 0.01
            and stability["one_way_random_effects_icc"] >= 0.75,
            "evidence": {
                "stable_task_fraction": stability[
                    "stable_task_fraction"
                ],
                "repeat_gain_range": stability["repeat_gain_range"],
                "icc": stability["one_way_random_effects_icc"],
            },
        },
        {
            "check_id": "CF08-SENSITIVITY-GRID",
            "passed": {
                row["minimum_meaningful_accuracy_gain"]
                for row in options
            }
            == set(EFFECT_GRID)
            and {row["target_power"] for row in options}
            == set(POWER_TARGETS),
            "evidence": "effect grid=5/8/10pp; power targets=80/90%",
        },
        {
            "check_id": "CF08-NOT-AUTO-FROZEN",
            "passed": candidate["approval_status"] == "pending"
            and candidate["formal_repeat_count_frozen"] is False
            and candidate["formal_sample_size_frozen"] is False,
            "evidence": "candidate requires explicit approval",
        },
    ]
    candidate_ready = all(row["passed"] for row in checks)
    report = {
        "schema_version": "1.0",
        "analysis_id": "V11-CF08-POWER-CANDIDATE-20260731",
        "check_id": "CF-08",
        "status": "in_progress" if candidate_ready else "failed",
        "candidate_status": "ready_for_review" if candidate_ready else "failed",
        "planning_method": {
            "estimand": (
                "Accuracy(Forced Verified Tool + Oracle Parameters) - "
                "Accuracy(No Tool)"
            ),
            "independent_unit": "base_task_group_id",
            "approximation": (
                "normal planning approximation on independent group-level "
                "accuracy gains"
            ),
            "alpha": ALPHA_ONE_SIDED,
            "test_direction": "one_sided_positive_gain",
            "pilot_uncertainty_inflation": (
                PILOT_UNCERTAINTY_INFLATION
            ),
            "limitations": [
                "The pilot contains only 26 base task groups.",
                "The normal approximation is a planning tool, not the final analysis.",
                "Tool-family heterogeneity is preserved by balanced allocation.",
                "The 5 percentage-point meaningful effect is proposed, not approved.",
            ],
        },
        "pilot_group_variation": {
            "base_task_group_count": len(group_values),
            "positive_group_count": sum(value > 0 for value in group_values),
            "zero_group_count": sum(value == 0 for value in group_values),
            "negative_group_count": sum(value < 0 for value in group_values),
            "group_equal_mean_accuracy_gain": mean(group_values),
            "group_median_accuracy_gain": median(group_values),
            "group_standard_deviation": group_sd,
            "minimum_group_gain": min(group_values),
            "maximum_group_gain": max(group_values),
        },
        "repeat_stability": stability,
        "recommended_candidate": candidate,
        "checks": checks,
        "pending_decisions": [
            "approve or revise the 5 percentage-point meaningful effect",
            "approve or revise 80% target power and one-sided alpha=0.05",
            "approve or revise 120 balanced base task groups",
            "approve or revise three model-run repeats",
        ],
        "cf03_may_be_marked_passed": False,
        "cf08_may_be_marked_passed": False,
        "core_frozen": False,
    }

    output_dir.mkdir(parents=True)
    report_path = output_dir / "cf08_power_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    options_path = output_dir / "sample_size_options.csv"
    write_csv(options_path, options)
    repeat_path = output_dir / "repeat_stability.csv"
    write_csv(repeat_path, stability["repeat_level_accuracy_gains"])

    source_paths = [
        POWER_INPUT_PATH,
        CF03_MANIFEST_PATH,
        BENEFIT_RECORDS_PATH,
        GROUP_EFFECTS_PATH,
        BENEFIT_REPORT_PATH,
        Path(__file__),
    ]
    manifest = {
        "schema_version": "1.0",
        "analysis_id": report["analysis_id"],
        "artifacts": [
            {"filename": path.name, "sha256": file_hash(path)}
            for path in (report_path, options_path, repeat_path)
        ],
        "source_artifacts": [
            {"filename": relative(path), "sha256": file_hash(path)}
            for path in source_paths
        ],
        "cf08_status": report["status"],
        "core_frozen": False,
    }
    (output_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "v11_cf08_power_20260731",
    )
    args = parser.parse_args()
    report = run_analysis(args.output_dir)
    print(
        json.dumps(
            {
                "analysis_id": report["analysis_id"],
                "cf08_status": report["status"],
                "candidate_status": report["candidate_status"],
                "recommended_candidate": report["recommended_candidate"],
                "core_frozen": report["core_frozen"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["candidate_status"] == "ready_for_review" else 1


if __name__ == "__main__":
    raise SystemExit(main())
