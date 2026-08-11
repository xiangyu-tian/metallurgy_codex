"""Offline four-metric scoring for A002/A003 Full Schema R1."""

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

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common


CONFIG_PATH = Path(__file__).with_name("a002_a003_full_schema_r1_analysis_config_v1.json")
METRICS = ["primary_endpoint_hit", "family_hit", "alternative_hit", "scientific_hit", "arguments_exact", "primary_end_to_end", "scientific_end_to_end"]


def score_rows(config: dict[str, Any], results: list[dict[str, Any]], scoring: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gold = {(row["task_id"], row["view_id"]): row for row in scoring}
    task_by_id = {row["task_id"]: row for row in tasks}
    if len(results) != config["expected_result_count"]:
        raise ValueError("runtime result count changed")
    rows = []
    for result in results:
        key = (result["task_id"], result["view_id"])
        if key not in gold:
            raise ValueError(f"missing scoring row: {key}")
        target = gold[key]
        expected_args = task_by_id[result["task_id"]]["canonical_inputs"]
        one_call = result["exactly_one_tool_call"] is True
        selected = result["selected_tool_id"] if one_call else None
        arguments_exact = one_call and result["arguments_json_valid"] is True and result["arguments"] == expected_args
        primary = selected in target["primary_acceptable_tools"] if selected else False
        family = selected in target["family_hit_tools"] if selected else False
        alternative = selected in target["alternative_success_tools"] if selected else False
        scientific = selected in target["scientific_success_tools"] if selected else False
        if not one_call:
            error_type = "no_single_tool_call_length" if result.get("finish_reason") == "length" else "no_single_tool_call_other"
        elif not result["arguments_json_valid"]:
            error_type = "invalid_arguments_json"
        elif result["arguments"] != expected_args:
            error_type = "arguments_mismatch"
        elif primary:
            error_type = "none"
        elif alternative:
            error_type = "alternative_endpoint_selected"
        elif family:
            error_type = "wrong_family_endpoint"
        else:
            error_type = "wrong_tool_family"
        raw_message = ((result.get("raw_response") or {}).get("choices") or [{}])[0].get("message", {})
        rows.append({
            "cell_id": result["cell_id"], "task_id": result["task_id"], "pair_id": result["pair_id"], "pair_variant": result["pair_variant"], "view_id": result["view_id"], "tool_pool_size": result["tool_pool_size"], "pool_repeat": result["pool_repeat"], "selected_tool_id": selected, "exactly_one_tool_call": one_call, "arguments_json_valid": result["arguments_json_valid"], "arguments_exact": arguments_exact,
            "primary_endpoint_hit": primary, "family_hit": family, "alternative_hit": alternative, "scientific_hit": scientific, "primary_end_to_end": primary and arguments_exact, "scientific_end_to_end": scientific and arguments_exact,
            "finish_reason": result.get("finish_reason"), "error_type": error_type, "reasoning_content_observed": bool(raw_message.get("reasoning_content")), "reasoning_token_count": ((result.get("usage") or {}).get("completion_tokens_details") or {}).get("reasoning_tokens", 0), "api_latency_ms": result["api_latency_ms"],
        })
    if len({row["cell_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate scored cell")
    return rows


def summarize(rows: list[dict[str, Any]], group_type: str, keys: list[str]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(tuple(row[key] for key in keys), []).append(row)
    output = []
    for values, group in sorted(grouped.items(), key=lambda item: tuple(str(value) for value in item[0])):
        result: dict[str, Any] = {"group_type": group_type, **dict(zip(keys, values)), "n": len(group)}
        for metric in METRICS:
            count = sum(bool(row[metric]) for row in group)
            result[f"{metric}_count"] = count
            result[f"{metric}_rate"] = round(count / len(group), 6)
        output.append(result)
    return output


def build(config: dict[str, Any]) -> dict[str, Any]:
    paths = {name: common.validate_binding(binding) for name, binding in config["bindings"].items()}
    sources = {name: common.load_json(path) for name, path in paths.items()}
    if sources["governance_adoption"]["decision"] != "adopted":
        raise ValueError("family governance is not adopted")
    rows = score_rows(config, sources["runtime_results"]["results"], sources["scoring_registry"]["rows"], sources["router_tasks"]["tasks"])
    summaries = []
    for group_type, keys in (("overall", []), ("pool_size", ["tool_pool_size"]), ("pool_size_repeat", ["tool_pool_size", "pool_repeat"]), ("pair_variant", ["pair_variant"]), ("pool_size_pair_variant", ["tool_pool_size", "pair_variant"])):
        summaries.extend(summarize(rows, group_type, keys))
    overall = next(row for row in summaries if row["group_type"] == "overall")
    by_size = {row["tool_pool_size"]: row for row in summaries if row["group_type"] == "pool_size"}
    length_failures = sum(row["error_type"] == "no_single_tool_call_length" for row in rows)
    reasoning_observed = sum(row["reasoning_content_observed"] for row in rows)
    report = {
        "schema_version": "1.0", "analysis_id": config["analysis_id"], "status": "development_r1_scored_transport_confound_detected", "result_count": len(rows),
        "overall": {metric: overall[f"{metric}_rate"] for metric in METRICS},
        "scale_difference_120_minus_17": {metric: round(by_size[120][f"{metric}_rate"] - by_size[17][f"{metric}_rate"], 6) for metric in METRICS},
        "error_counts": dict(sorted(Counter(row["error_type"] for row in rows).items())),
        "length_terminated_no_call_count": length_failures, "reasoning_content_observed_count": reasoning_observed,
        "transport_confound": {"detected": reasoning_observed > 0, "description": "opening config declared thinking disabled, but the materialized payload omitted an explicit thinking field and provider responses contained reasoning content/tokens; all six end-to-end failures occurred at 120 tools and were length-related or truncated arguments", "confirmatory_interpretation_allowed": False},
        "external_api_calls": 64, "tool_calls_executed": 0, "retries_executed": 0, "independent_validation_split_accessed": False, "confirmatory_inference_allowed": False, "cf05_status": "in_progress", "core_frozen": False,
        "next_gate": "freeze a transport-corrected development R1.1 payload with explicit thinking disabled and sufficient output budget, then request separate authorization; do not retry or overwrite R1",
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
    common.write_json(output_dir / "a002_a003_full_schema_r1_analysis_config_snapshot.json", config)
    common.write_json(output_dir / "a002_a003_full_schema_r1_scored_rows.json", {"schema_version": "1.0", "rows": result["rows"]})
    write_csv(output_dir / "a002_a003_full_schema_r1_scored_rows.csv", result["rows"])
    common.write_json(output_dir / "a002_a003_full_schema_r1_summary.json", {"schema_version": "1.0", "rows": result["summaries"]})
    write_csv(output_dir / "a002_a003_full_schema_r1_summary.csv", result["summaries"])
    common.write_json(output_dir / "a002_a003_full_schema_r1_analysis_report.json", result["report"])
    paths = sorted(output_dir.iterdir(), key=lambda path: path.name)
    common.write_json(output_dir / "artifact_manifest.json", {"schema_version": "1.0", "analysis_id": config["analysis_id"], "artifact_count": len(paths), "artifacts": [{"filename": path.name, "sha256": common.file_hash(path), "bytes": path.stat().st_size} for path in paths]})
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
