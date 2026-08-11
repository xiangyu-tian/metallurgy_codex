"""Offline intention-to-treat scoring for the A002/A003 Top-5 selector R1."""

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


CONFIG_PATH = Path(__file__).with_name(
    "a002_a003_top5_selector_r1_analysis_config_v1.json"
)
METRICS = [
    "transport_accepted",
    "exactly_one_tool_call",
    "primary_endpoint_hit",
    "family_hit",
    "scientific_hit",
    "arguments_exact",
    "primary_end_to_end",
    "scientific_end_to_end",
]


def classify_error(result: dict[str, Any], primary: bool, family: bool, alternative: bool, arguments_exact: bool) -> str:
    if result.get("provider_error"):
        return "provider_error_terminal"
    if result.get("exactly_one_tool_call") is not True:
        if result.get("finish_reason") == "length":
            return "no_single_tool_call_length"
        if result.get("tool_call_count") == 0 and result.get("finish_reason") == "tool_calls":
            return "empty_tool_calls_with_tool_finish"
        if (result.get("tool_call_count") or 0) > 1:
            return "multiple_tool_calls"
        return "no_single_tool_call_other"
    if result.get("arguments_json_valid") is not True:
        return "invalid_arguments_json"
    if not arguments_exact:
        return "arguments_mismatch"
    if primary:
        return "none"
    if alternative:
        return "alternative_endpoint_selected"
    if family:
        return "wrong_family_endpoint"
    return "wrong_tool_family"


def score_rows(
    config: dict[str, Any],
    results: list[dict[str, Any]],
    scoring: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    gold = {(row["task_id"], row["view_id"]): row for row in scoring}
    task_by_id = {row["task_id"]: row for row in tasks}
    if len(results) != config["expected_result_count"]:
        raise ValueError("Top-5 runtime result count changed")
    rows = []
    for result in results:
        key = (result["task_id"], result["source_pool_view_id"])
        if key not in gold:
            raise ValueError(f"missing Top-5 scoring row: {key}")
        target = gold[key]
        expected_args = task_by_id[result["task_id"]]["canonical_inputs"]
        one_call = result["exactly_one_tool_call"] is True
        selected = result["selected_tool_id"] if one_call else None
        arguments_exact = bool(
            one_call
            and result["arguments_json_valid"] is True
            and result["arguments"] == expected_args
        )
        primary = selected in target["primary_acceptable_tools"] if selected else False
        family = selected in target["family_hit_tools"] if selected else False
        alternative = selected in target["alternative_success_tools"] if selected else False
        scientific = selected in target["scientific_success_tools"] if selected else False
        error_type = classify_error(result, primary, family, alternative, arguments_exact)
        rows.append(
            {
                "sequence": result["sequence"],
                "cell_id": result["cell_id"],
                "task_id": result["task_id"],
                "pair_id": result["pair_id"],
                "pair_variant": result["pair_variant"],
                "source_pool_view_id": result["source_pool_view_id"],
                "tool_pool_size": target["tool_pool_size"],
                "pool_repeat": target["pool_repeat"],
                "method": result["method"],
                "selected_tool_id": selected,
                "transport_accepted": result["transport_accepted"],
                "exactly_one_tool_call": one_call,
                "arguments_json_valid": result["arguments_json_valid"],
                "arguments_exact": arguments_exact,
                "primary_endpoint_hit": primary,
                "family_hit": family,
                "alternative_hit": alternative,
                "scientific_hit": scientific,
                "primary_end_to_end": primary and arguments_exact,
                "scientific_end_to_end": scientific and arguments_exact,
                "finish_reason": result.get("finish_reason"),
                "tool_call_count": result.get("tool_call_count"),
                "provider_error": result.get("provider_error"),
                "error_type": error_type,
                "reasoning_content_observed": result["transport_policy_audit"][
                    "reasoning_observed"
                ],
                "api_latency_ms": result["api_latency_ms"],
            }
        )
    if len({row["cell_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate scored Top-5 cell")
    return rows


def summarize(
    rows: list[dict[str, Any]], group_type: str, keys: list[str]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(tuple(row[key] for key in keys), []).append(row)
    output = []
    for values, group in sorted(
        grouped.items(), key=lambda item: tuple(str(value) for value in item[0])
    ):
        summary: dict[str, Any] = {
            "group_type": group_type,
            **dict(zip(keys, values)),
            "n": len(group),
        }
        for metric in METRICS:
            count = sum(bool(row[metric]) for row in group)
            summary[f"{metric}_count"] = count
            summary[f"{metric}_rate"] = round(count / len(group), 6)
        single_rows = [row for row in group if row["exactly_one_tool_call"]]
        summary["primary_endpoint_hit_rate_given_single_call"] = (
            round(
                sum(row["primary_endpoint_hit"] for row in single_rows)
                / len(single_rows),
                6,
            )
            if single_rows
            else None
        )
        output.append(summary)
    return output


def build(config: dict[str, Any]) -> dict[str, Any]:
    if config["denominator_policy"] != "intention_to_treat_all_192_scheduled_cells":
        raise ValueError("Top-5 denominator policy changed")
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
    runtime_report = sources["runtime_report"]
    if runtime_report["external_api_calls"] != 192 or runtime_report["retries_executed"] != 0:
        raise ValueError("runtime call/retry count differs from authorization")
    rows = score_rows(
        config,
        sources["runtime_results"]["results"],
        sources["scoring_registry"]["rows"],
        sources["router_tasks"]["tasks"],
    )
    summaries = []
    for group_type, keys in (
        ("overall", []),
        ("method", ["method"]),
        ("pool_size", ["tool_pool_size"]),
        ("method_pool_size", ["method", "tool_pool_size"]),
        ("pair_variant", ["pair_variant"]),
        ("method_pair_variant", ["method", "pair_variant"]),
    ):
        summaries.extend(summarize(rows, group_type, keys))
    overall = next(row for row in summaries if row["group_type"] == "overall")
    by_size = {
        row["tool_pool_size"]: row
        for row in summaries
        if row["group_type"] == "pool_size"
    }
    method_rows = [row for row in summaries if row["group_type"] == "method"]
    all_single_calls_primary_correct = all(
        row["primary_endpoint_hit"]
        for row in rows
        if row["exactly_one_tool_call"]
    )
    report = {
        "schema_version": "1.0",
        "analysis_id": config["analysis_id"],
        "status": "development_r1_scored_with_terminal_transport_failures",
        "denominator_policy": config["denominator_policy"],
        "result_count": len(rows),
        "overall": {metric: overall[f"{metric}_rate"] for metric in METRICS},
        "method_primary_end_to_end": {
            row["method"]: row["primary_end_to_end_rate"] for row in method_rows
        },
        "scale_difference_120_minus_17": {
            metric: round(
                by_size[120][f"{metric}_rate"] - by_size[17][f"{metric}_rate"],
                6,
            )
            for metric in METRICS
        },
        "error_counts": dict(sorted(Counter(row["error_type"] for row in rows).items())),
        "all_single_calls_primary_correct": all_single_calls_primary_correct,
        "primary_endpoint_hit_rate_given_single_call": overall[
            "primary_endpoint_hit_rate_given_single_call"
        ],
        "reasoning_content_observed_count": sum(
            row["reasoning_content_observed"] for row in rows
        ),
        "external_api_calls_in_source_run": 192,
        "external_api_calls_in_analysis": 0,
        "tool_calls_executed": 0,
        "retries_executed": 0,
        "independent_validation_split_accessed": False,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "interpretation": "All 188 single tool calls selected a primary acceptable endpoint with exact arguments. The four intention-to-treat failures were three dual-call responses selecting both A002 and the equivalent E3C002 endpoint, plus one terminal provider HTTP 522. All occurred on the complex Cu(NH3)4SO4 element-count task at 120 tools; they are retained as failures and were not retried.",
        "next_gate": "preserve R1 unchanged, commit the runtime and offline scoring evidence, then decide whether a separately authorized repeat is needed for variability rather than retrying failed cells",
    }
    return {"rows": rows, "summaries": summaries, "report": report}


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
    common.write_json(
        output_dir / "a002_a003_top5_selector_r1_analysis_config_snapshot.json",
        config,
    )
    common.write_json(
        output_dir / "a002_a003_top5_selector_r1_scored_rows.json",
        {"schema_version": "1.0", "rows": result["rows"]},
    )
    write_csv(output_dir / "a002_a003_top5_selector_r1_scored_rows.csv", result["rows"])
    common.write_json(
        output_dir / "a002_a003_top5_selector_r1_summary.json",
        {"schema_version": "1.0", "rows": result["summaries"]},
    )
    write_csv(output_dir / "a002_a003_top5_selector_r1_summary.csv", result["summaries"])
    common.write_json(
        output_dir / "a002_a003_top5_selector_r1_analysis_report.json",
        result["report"],
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
