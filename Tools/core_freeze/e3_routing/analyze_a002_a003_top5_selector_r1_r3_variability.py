"""Score and compare the three frozen A002/A003 Top-5 selector repeats."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common  # noqa: E402
from Tools.core_freeze.e3_routing.analyze_a002_a003_top5_selector_r1 import (  # noqa: E402
    METRICS,
    score_rows,
    summarize,
)


CONFIG_PATH = Path(__file__).with_name(
    "a002_a003_top5_selector_r1_r3_variability_config_v1.json"
)


def _score_repeat_set(
    results: list[dict[str, Any]],
    scoring: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = score_rows(
        {"expected_result_count": len(results)}, results, scoring, tasks
    )
    result_by_cell = {row["cell_id"]: row for row in results}
    for row in rows:
        source = result_by_cell[row["cell_id"]]
        row["model_run_repeat"] = source["model_run_repeat"]
        row["repeat_unit_id"] = source.get("source_r1_cell_id", source["cell_id"])
    return rows


def _outcome_token(row: dict[str, Any]) -> str:
    if row["exactly_one_tool_call"]:
        return f"single:{row['selected_tool_id']}:{row['arguments_exact']}"
    return f"failure:{row['error_type']}"


def build(config: dict[str, Any]) -> dict[str, Any]:
    if config["denominator_policy"] != "intention_to_treat_all_576_scheduled_cells":
        raise ValueError("three-repeat denominator policy changed")
    if config["provider_failures_and_non_single_calls_count_as_incorrect"] is not True:
        raise ValueError("terminal failures must count as incorrect")
    for field in (
        "automatic_retry_allowed",
        "confirmatory_inference_allowed",
        "independent_validation_split_access_allowed",
        "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")
    paths = {
        name: common.validate_binding(binding)
        for name, binding in config["bindings"].items()
    }
    sources = {name: common.load_json(path) for name, path in paths.items()}
    if sources["governance_adoption"]["decision"] != "adopted":
        raise ValueError("A002/A003 family governance is not adopted")
    if (
        sources["r1_runtime_report"]["external_api_calls"] != 192
        or sources["r1_runtime_report"]["retries_executed"] != 0
        or sources["r2_r3_runtime_report"]["external_api_calls"] != 384
        or sources["r2_r3_runtime_report"]["retries_executed"] != 0
    ):
        raise ValueError("runtime call/retry count differs from authorization")

    scoring = sources["scoring_registry"]["rows"]
    tasks = sources["router_tasks"]["tasks"]
    r1_results = sources["r1_runtime_results"]["results"]
    later_results = sources["r2_r3_runtime_results"]["results"]
    rows = _score_repeat_set(r1_results, scoring, tasks) + _score_repeat_set(
        later_results, scoring, tasks
    )
    if len(rows) != config["expected_result_count"]:
        raise ValueError("three-repeat result count changed")
    if Counter(row["model_run_repeat"] for row in rows) != Counter(
        {"R1": 192, "R2": 192, "R3": 192}
    ):
        raise ValueError("three-repeat grid is incomplete")

    units: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        units.setdefault(row["repeat_unit_id"], []).append(row)
    if len(units) != config["expected_unit_count"]:
        raise ValueError("matched repeat unit count changed")
    unit_rows = []
    for unit_id, group in sorted(units.items()):
        by_repeat = {row["model_run_repeat"]: row for row in group}
        if set(by_repeat) != {"R1", "R2", "R3"} or len(group) != 3:
            raise ValueError(f"incomplete matched repeat unit: {unit_id}")
        correctness = [by_repeat[repeat]["primary_end_to_end"] for repeat in config["model_run_repeats"]]
        outcome_tokens = [_outcome_token(by_repeat[repeat]) for repeat in config["model_run_repeats"]]
        first = by_repeat["R1"]
        unit_rows.append(
            {
                "repeat_unit_id": unit_id,
                "task_id": first["task_id"],
                "pair_id": first["pair_id"],
                "pair_variant": first["pair_variant"],
                "source_pool_view_id": first["source_pool_view_id"],
                "tool_pool_size": first["tool_pool_size"],
                "pool_repeat": first["pool_repeat"],
                "method": first["method"],
                "r1_primary_end_to_end": correctness[0],
                "r2_primary_end_to_end": correctness[1],
                "r3_primary_end_to_end": correctness[2],
                "correct_repeat_count": sum(correctness),
                "primary_end_to_end_stable": len(set(correctness)) == 1,
                "stable_correct": all(correctness),
                "stable_failure": not any(correctness),
                "variable_correctness": len(set(correctness)) > 1,
                "r1_outcome": outcome_tokens[0],
                "r2_outcome": outcome_tokens[1],
                "r3_outcome": outcome_tokens[2],
                "exact_outcome_stable": len(set(outcome_tokens)) == 1,
            }
        )

    summaries = []
    for group_type, keys in (
        ("overall", []),
        ("repeat", ["model_run_repeat"]),
        ("repeat_method", ["model_run_repeat", "method"]),
        ("repeat_pool_size", ["model_run_repeat", "tool_pool_size"]),
        ("method", ["method"]),
        ("pool_size", ["tool_pool_size"]),
    ):
        summaries.extend(summarize(rows, group_type, keys))
    repeat_summaries = {
        row["model_run_repeat"]: row
        for row in summaries
        if row["group_type"] == "repeat"
    }
    repeat_size = {
        (row["model_run_repeat"], row["tool_pool_size"]): row
        for row in summaries
        if row["group_type"] == "repeat_pool_size"
    }
    pairwise = []
    for left, right in (("R1", "R2"), ("R1", "R3"), ("R2", "R3")):
        left_key = f"{left.lower()}_primary_end_to_end"
        right_key = f"{right.lower()}_primary_end_to_end"
        agreement = sum(row[left_key] == row[right_key] for row in unit_rows)
        pairwise.append(
            {
                "repeat_left": left,
                "repeat_right": right,
                "n": len(unit_rows),
                "primary_end_to_end_agreement_count": agreement,
                "primary_end_to_end_agreement_rate": round(agreement / len(unit_rows), 6),
                "both_correct_count": sum(row[left_key] and row[right_key] for row in unit_rows),
                "left_only_correct_count": sum(row[left_key] and not row[right_key] for row in unit_rows),
                "right_only_correct_count": sum(not row[left_key] and row[right_key] for row in unit_rows),
                "both_incorrect_count": sum(not row[left_key] and not row[right_key] for row in unit_rows),
            }
        )

    method_variability = []
    for method in config["methods"]:
        group = [row for row in unit_rows if row["method"] == method]
        method_variability.append(
            {
                "method": method,
                "n": len(group),
                "stable_correct_count": sum(row["stable_correct"] for row in group),
                "stable_failure_count": sum(row["stable_failure"] for row in group),
                "variable_correctness_count": sum(row["variable_correctness"] for row in group),
                "variable_correctness_rate": round(
                    sum(row["variable_correctness"] for row in group) / len(group), 6
                ),
                "exact_outcome_stable_count": sum(row["exact_outcome_stable"] for row in group),
                "exact_outcome_stable_rate": round(
                    sum(row["exact_outcome_stable"] for row in group) / len(group), 6
                ),
            }
        )

    error_counts_by_repeat = {
        repeat: dict(
            sorted(
                Counter(
                    row["error_type"]
                    for row in rows
                    if row["model_run_repeat"] == repeat
                ).items()
            )
        )
        for repeat in config["model_run_repeats"]
    }
    report = {
        "schema_version": "1.0",
        "analysis_id": config["analysis_id"],
        "status": "development_three_repeat_variability_scored",
        "denominator_policy": config["denominator_policy"],
        "result_count": len(rows),
        "matched_unit_count": len(unit_rows),
        "repeat_primary_end_to_end": {
            repeat: repeat_summaries[repeat]["primary_end_to_end_rate"]
            for repeat in config["model_run_repeats"]
        },
        "repeat_exactly_one_tool_call": {
            repeat: repeat_summaries[repeat]["exactly_one_tool_call_rate"]
            for repeat in config["model_run_repeats"]
        },
        "repeat_scale_difference_120_minus_17": {
            repeat: round(
                repeat_size[(repeat, 120)]["primary_end_to_end_rate"]
                - repeat_size[(repeat, 17)]["primary_end_to_end_rate"],
                6,
            )
            for repeat in config["model_run_repeats"]
        },
        "stable_correct_count": sum(row["stable_correct"] for row in unit_rows),
        "stable_failure_count": sum(row["stable_failure"] for row in unit_rows),
        "variable_correctness_count": sum(row["variable_correctness"] for row in unit_rows),
        "variable_correctness_rate": round(
            sum(row["variable_correctness"] for row in unit_rows) / len(unit_rows), 6
        ),
        "exact_outcome_stable_count": sum(row["exact_outcome_stable"] for row in unit_rows),
        "exact_outcome_stable_rate": round(
            sum(row["exact_outcome_stable"] for row in unit_rows) / len(unit_rows), 6
        ),
        "error_counts_by_repeat": error_counts_by_repeat,
        "external_api_calls_in_source_runs": 576,
        "external_api_calls_in_analysis": 0,
        "tool_calls_executed": 0,
        "retries_executed": 0,
        "independent_validation_split_accessed": False,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "interpretation": "Development-only three-repeat variability evidence; non-single calls and provider failures remain intention-to-treat errors. This analysis does not access the independent validation split and cannot support confirmatory inference.",
        "next_gate": "review the three-repeat failure localization and decide whether the frozen Top-5 candidate definitions are sufficiently stable for CF-05 development closure",
    }
    return {
        "rows": rows,
        "unit_rows": unit_rows,
        "summaries": summaries,
        "pairwise": pairwise,
        "method_variability": method_variability,
        "report": report,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = common.load_json(CONFIG_PATH)
    result = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a002_a003_top5_selector_r1_r3_variability_config_snapshot.json": config,
        "a002_a003_top5_selector_r1_r3_scored_rows.json": {
            "schema_version": "1.0",
            "rows": result["rows"],
        },
        "a002_a003_top5_selector_r1_r3_unit_variability.json": {
            "schema_version": "1.0",
            "rows": result["unit_rows"],
        },
        "a002_a003_top5_selector_r1_r3_summary.json": {
            "schema_version": "1.0",
            "rows": result["summaries"],
        },
        "a002_a003_top5_selector_r1_r3_pairwise_agreement.json": {
            "schema_version": "1.0",
            "rows": result["pairwise"],
        },
        "a002_a003_top5_selector_r1_r3_method_variability.json": {
            "schema_version": "1.0",
            "rows": result["method_variability"],
        },
        "a002_a003_top5_selector_r1_r3_analysis_report.json": result["report"],
    }
    for filename, value in artifacts.items():
        common.write_json(output_dir / filename, value)
    write_csv(
        output_dir / "a002_a003_top5_selector_r1_r3_scored_rows.csv",
        result["rows"],
    )
    write_csv(
        output_dir / "a002_a003_top5_selector_r1_r3_unit_variability.csv",
        result["unit_rows"],
    )
    write_csv(
        output_dir / "a002_a003_top5_selector_r1_r3_summary.csv",
        result["summaries"],
    )
    write_csv(
        output_dir / "a002_a003_top5_selector_r1_r3_pairwise_agreement.csv",
        result["pairwise"],
    )
    write_csv(
        output_dir / "a002_a003_top5_selector_r1_r3_method_variability.csv",
        result["method_variability"],
    )
    paths = sorted(output_dir.iterdir(), key=lambda path: path.name)
    common.write_json(
        output_dir / "artifact_manifest.json",
        {
            "schema_version": "1.0",
            "analysis_id": config["analysis_id"],
            "artifact_count": len(paths),
            "artifacts": [
                {
                    "filename": path.name,
                    "sha256": common.file_hash(path),
                    "bytes": path.stat().st_size,
                }
                for path in paths
            ],
        },
    )
    return result["report"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else WORKSPACE / args.output_dir
    print(json.dumps(build_outputs(output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
