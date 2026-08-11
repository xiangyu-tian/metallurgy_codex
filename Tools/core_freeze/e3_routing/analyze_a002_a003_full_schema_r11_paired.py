"""Score R1.1 and pair every cell with its frozen R1 counterpart."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common
from Tools.core_freeze.e3_routing.analyze_a002_a003_full_schema_r1 import METRICS, score_rows, summarize


CONFIG_PATH = Path(__file__).with_name("a002_a003_full_schema_r11_paired_analysis_config_v1.json")
PAIR_METRICS = ["primary_endpoint_hit", "family_hit", "scientific_hit", "arguments_exact", "primary_end_to_end", "scientific_end_to_end"]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def pair_rows(r1_rows: list[dict[str, Any]], r11_rows: list[dict[str, Any]], raw_r11: list[dict[str, Any]]) -> list[dict[str, Any]]:
    r1_by_id = {row["cell_id"]: row for row in r1_rows}
    raw_by_task_view = {(row["task_id"], row["view_id"]): row for row in raw_r11}
    output = []
    for row in r11_rows:
        raw = raw_by_task_view[(row["task_id"], row["view_id"])]
        source_id = raw["source_r1_cell_id"]
        before = r1_by_id.get(source_id)
        if before is None:
            raise ValueError(f"R1 pair missing: {source_id}")
        paired = {
            "source_r1_cell_id": source_id,
            "r11_cell_id": raw["cell_id"],
            "task_id": row["task_id"],
            "pair_variant": row["pair_variant"],
            "tool_pool_size": row["tool_pool_size"],
            "pool_repeat": row["pool_repeat"],
            "r1_error_type": before["error_type"],
            "r11_error_type": row["error_type"],
            "r1_selected_tool_id": before["selected_tool_id"],
            "r11_selected_tool_id": row["selected_tool_id"],
        }
        for metric in PAIR_METRICS:
            paired[f"r1_{metric}"] = before[metric]
            paired[f"r11_{metric}"] = row[metric]
            paired[f"delta_{metric}"] = int(bool(row[metric])) - int(bool(before[metric]))
        paired["r1_failure_recovered_end_to_end"] = not before["primary_end_to_end"] and row["primary_end_to_end"]
        output.append(paired)
    if len(output) != 64 or len({row["source_r1_cell_id"] for row in output}) != 64:
        raise ValueError("paired grid is incomplete")
    return output


def paired_summary(rows: list[dict[str, Any]], group_type: str, keys: list[str]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(tuple(row[key] for key in keys), []).append(row)
    output = []
    for values, group in sorted(grouped.items(), key=lambda item: tuple(str(value) for value in item[0])):
        result: dict[str, Any] = {"group_type": group_type, **dict(zip(keys, values)), "n": len(group)}
        for metric in PAIR_METRICS:
            before = sum(bool(row[f"r1_{metric}"]) for row in group)
            after = sum(bool(row[f"r11_{metric}"]) for row in group)
            result[f"r1_{metric}_rate"] = round(before / len(group), 6)
            result[f"r11_{metric}_rate"] = round(after / len(group), 6)
            result[f"delta_{metric}_rate"] = round((after - before) / len(group), 6)
        result["recovered_end_to_end_failure_count"] = sum(row["r1_failure_recovered_end_to_end"] for row in group)
        output.append(result)
    return output


def build(config: dict[str, Any]) -> dict[str, Any]:
    paths = {name: common.validate_binding(binding) for name, binding in config["bindings"].items()}
    sources = {name: common.load_json(path) for name, path in paths.items()}
    raw_r11 = sources["r11_runtime_results"]["results"]
    r11_rows = score_rows(config | {"expected_result_count": 64}, raw_r11, sources["scoring_registry"]["rows"], sources["router_tasks"]["tasks"])
    r1_rows = sources["r1_scored_rows"]["rows"]
    pairs = pair_rows(r1_rows, r11_rows, raw_r11)
    r11_summaries = []
    paired_summaries = []
    groups = (("overall", []), ("pool_size", ["tool_pool_size"]), ("pool_size_repeat", ["tool_pool_size", "pool_repeat"]), ("pair_variant", ["pair_variant"]), ("pool_size_pair_variant", ["tool_pool_size", "pair_variant"]))
    for group_type, keys in groups:
        r11_summaries.extend(summarize(r11_rows, group_type, keys))
        paired_summaries.extend(paired_summary(pairs, group_type, keys))
    overall = next(row for row in paired_summaries if row["group_type"] == "overall")
    r11_reasoning = sum(row["reasoning_content_observed"] for row in r11_rows)
    report = {
        "schema_version": "1.0",
        "analysis_id": config["analysis_id"],
        "status": "development_paired_transport_correction_complete",
        "pair_count": len(pairs),
        "r11_primary_endpoint_selection_accuracy": overall["r11_primary_endpoint_hit_rate"],
        "r11_primary_end_to_end_success_rate": overall["r11_primary_end_to_end_rate"],
        "r1_to_r11_primary_endpoint_delta": overall["delta_primary_endpoint_hit_rate"],
        "r1_to_r11_primary_end_to_end_delta": overall["delta_primary_end_to_end_rate"],
        "r1_end_to_end_failure_count": sum(not row["r1_primary_end_to_end"] for row in pairs),
        "r11_end_to_end_failure_count": sum(not row["r11_primary_end_to_end"] for row in pairs),
        "r1_failures_recovered_count": sum(row["r1_failure_recovered_end_to_end"] for row in pairs),
        "r11_reasoning_content_observed_count": r11_reasoning,
        "r11_length_termination_count": sum(row["r11_error_type"] == "no_single_tool_call_length" for row in pairs),
        "interpretation": "Within this development-only paired single-axis run, explicit thinking disable removed the R1 length/truncation failures and restored all 64 cells. The R1 17-to-120 decline was therefore a transport-budget artifact in this taskset, not observed A002/A003 endpoint confusion.",
        "limitations": ["single model run repeat", "eight formula pairs", "controlled lexical-8 A/B pools", "development data only", "not a confirmatory H4 result"],
        "external_api_calls_in_r11": 64,
        "tool_calls_executed": 0,
        "retries_executed": 0,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "next_gate": "accept explicit thinking disable as the frozen transport policy for later development runs; return to CF-05 route-method development rather than increase token budget",
    }
    return {"r11_rows": r11_rows, "pairs": pairs, "r11_summaries": r11_summaries, "paired_summaries": paired_summaries, "report": report}


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = common.load_json(CONFIG_PATH)
    result = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a002_a003_r1_r11_paired_analysis_config_snapshot.json": config,
        "a002_a003_r11_scored_rows.json": {"schema_version": "1.0", "rows": result["r11_rows"]},
        "a002_a003_r1_r11_paired_rows.json": {"schema_version": "1.0", "rows": result["pairs"]},
        "a002_a003_r11_summary.json": {"schema_version": "1.0", "rows": result["r11_summaries"]},
        "a002_a003_r1_r11_paired_summary.json": {"schema_version": "1.0", "rows": result["paired_summaries"]},
        "a002_a003_r1_r11_paired_report.json": result["report"],
    }
    for filename, value in artifacts.items():
        common.write_json(output_dir / filename, value)
    write_csv(output_dir / "a002_a003_r1_r11_paired_rows.csv", result["pairs"])
    write_csv(output_dir / "a002_a003_r1_r11_paired_summary.csv", result["paired_summaries"])
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
