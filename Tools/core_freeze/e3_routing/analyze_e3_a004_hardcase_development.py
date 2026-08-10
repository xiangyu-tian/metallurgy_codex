"""Offline scoring for the completed A004 hard-case controlled-neighbor run."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Callable


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("a004_hardcase_analysis_config_v1.json")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_binding(binding: dict[str, str]) -> Path:
    path = WORKSPACE / binding["path"]
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = file_hash(path)
    if actual != binding["sha256"].lower():
        raise ValueError(f"bound file hash mismatch for {path}: {actual}")
    return path


def validate_config(config: dict[str, Any]) -> None:
    if config["run_id"] != "V11-CF05-E3-A004-HARDCASE-R1-20260810":
        raise ValueError("unexpected run identity")
    if config["expected_result_count"] != 48 or config["expected_task_count"] != 2:
        raise ValueError("development grid changed")
    if config["neighbor_conditions"] != ["none_0", "lexical_4", "contract_mismatch_4"]:
        raise ValueError("neighbor conditions changed")
    if config["methods"] != ["full_schema", "lexical_top5", "dense_top5", "hierarchical"]:
        raise ValueError("method set changed")
    if config["tool_pool_sizes"] != [17, 120]:
        raise ValueError("tool-pool sizes changed")
    if config["development_only"] is not True or config["confirmatory_inference_allowed"] is not False or config["core_frozen"] is not False:
        raise ValueError("analysis policy changed")


def values_equal(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual is expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return float(actual) == float(expected)
    if isinstance(actual, dict) and isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(values_equal(actual[key], expected[key]) for key in actual)
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(values_equal(left, right) for left, right in zip(actual, expected))
    return actual == expected


def parameters_compatible(actual: Any, expected: Any, schema: dict[str, Any]) -> bool:
    if not isinstance(actual, dict) or not isinstance(expected, dict) or not set(expected).issubset(actual):
        return False
    if not all(values_equal(actual[key], expected[key]) for key in expected):
        return False
    properties = schema.get("properties", {})
    for key in set(actual).difference(expected):
        property_schema = properties.get(key)
        if not isinstance(property_schema, dict) or "default" not in property_schema:
            return False
        if not values_equal(actual[key], property_schema["default"]):
            return False
    return True


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot summarize empty rows")
    prompt_tokens = [(row.get("usage") or {}).get("prompt_tokens") for row in rows]
    completion_tokens = [(row.get("usage") or {}).get("completion_tokens") for row in rows]
    return {
        "cell_count": len(rows),
        "transport_acceptance_rate": mean(row["transport_accepted"] for row in rows),
        "single_tool_call_rate": mean(row["exactly_one_tool_call"] for row in rows),
        "target_tool_selection_accuracy": mean(row["selection_correct"] for row in rows),
        "parameter_accuracy": mean(row["parameters_correct"] for row in rows),
        "complete_call_accuracy": mean(row["complete_call_correct"] for row in rows),
        "mean_api_latency_ms": mean(row["api_latency_ms"] for row in rows),
        "mean_prompt_tokens": mean(value for value in prompt_tokens if isinstance(value, int)),
        "mean_completion_tokens": mean(value for value in completion_tokens if isinstance(value, int)),
    }


def grouped(rows: list[dict[str, Any]], key_fn: Callable[[dict[str, Any]], tuple[Any, ...]],
            names: tuple[str, ...]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[key_fn(row)].append(row)
    return [{**dict(zip(names, key)), **summarize(group)} for key, group in sorted(groups.items())]


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {name: validate_binding(binding) for name, binding in config["bindings"].items()}
    result_payload = load_json(paths["request_results"])
    runtime = load_json(paths["runtime_report"])
    scoring = load_json(paths["scoring_registry"])
    candidate_views = load_json(paths["candidate_views"])
    results = result_payload["results"]
    if result_payload["run_id"] != config["run_id"] or len(results) != 48:
        raise ValueError("request result identity or count changed")
    if len({row["cell_id"] for row in results}) != 48:
        raise ValueError("duplicate result cells")
    if Counter(row["method"] for row in results) != Counter({method: 12 for method in config["methods"]}):
        raise ValueError("method grid incomplete")
    if Counter(row["condition_id"] for row in results) != Counter({condition: 16 for condition in config["neighbor_conditions"]}):
        raise ValueError("condition grid incomplete")
    if Counter(row["tool_pool_size"] for row in results) != Counter({17: 24, 120: 24}):
        raise ValueError("size grid incomplete")
    if runtime["external_api_calls"] != 48 or runtime["transport_accepted_count"] != 48 or runtime["provider_error_count"] != 0:
        raise ValueError("runtime transport contract failed")
    if runtime["tool_calls_executed"] != 0 or runtime["retries_executed"] != 0 or runtime["independent_validation_split_accessed"] is not False:
        raise ValueError("runtime safety contract failed")
    gold_by_task = {row["task_id"]: row for row in scoring["tasks"]}
    if len(gold_by_task) != 2:
        raise ValueError("scoring task count changed")
    schemas_by_view = {
        view["candidate_view_id"]: {tool["function"]["name"]: tool["function"]["parameters"] for tool in view["openai_tools"]}
        for view in candidate_views["views"]
    }
    scored_rows = []
    for row in results:
        gold = gold_by_task[row["task_id"]]
        visible = set(row["selected_schema_tool_ids"])
        if "A004" not in visible:
            raise ValueError(f"A004 missing from submitted view: {row['cell_id']}")
        selected_visible = row["selected_tool_id"] in visible
        selection_correct = bool(row["transport_accepted"] and row["exactly_one_tool_call"]
                                 and selected_visible and row["selected_tool_id"] == "A004")
        selected_schema = schemas_by_view.get(row["candidate_view_id"], {}).get(row["selected_tool_id"])
        parameters_correct = bool(row["exactly_one_tool_call"] and isinstance(selected_schema, dict)
                                  and row["arguments_json_valid"]
                                  and parameters_compatible(row["arguments"], gold["expected_parameters"], selected_schema))
        scored_rows.append({
            "cell_id": row["cell_id"], "task_id": row["task_id"], "target_tool_id": "A004",
            "condition_id": row["condition_id"], "near_neighbor_type": row["near_neighbor_type"],
            "near_neighbor_count": row["near_neighbor_count"], "tool_pool_size": row["tool_pool_size"],
            "method": row["method"], "candidate_view_id": row["candidate_view_id"],
            "transport_accepted": row["transport_accepted"], "tool_call_count": row["tool_call_count"],
            "exactly_one_tool_call": row["exactly_one_tool_call"], "selected_tool_id": row["selected_tool_id"],
            "selected_tool_visible": selected_visible, "selection_correct": selection_correct,
            "arguments": row["arguments"], "expected_parameters": gold["expected_parameters"],
            "parameters_correct": parameters_correct,
            "complete_call_correct": selection_correct and parameters_correct,
            "api_latency_ms": row["api_latency_ms"], "usage": row["usage"],
            "tool_executed": row["tool_executed"], "retry_count": row["retry_count"],
        })
    overall = summarize(scored_rows)
    by_condition = grouped(scored_rows, lambda row: (row["condition_id"],), ("condition_id",))
    by_method = grouped(scored_rows, lambda row: (row["method"],), ("method",))
    by_size = grouped(scored_rows, lambda row: (row["tool_pool_size"],), ("tool_pool_size",))
    by_condition_method_size = grouped(
        scored_rows, lambda row: (row["condition_id"], row["method"], row["tool_pool_size"]),
        ("condition_id", "method", "tool_pool_size"))
    condition_map = {row["condition_id"]: row for row in by_condition}
    contrasts = []
    for condition in ("lexical_4", "contract_mismatch_4"):
        contrasts.append({
            "contrast": f"{condition}_minus_none_0",
            "complete_call_accuracy_difference": condition_map[condition]["complete_call_accuracy"] - condition_map["none_0"]["complete_call_accuracy"],
            "interpretation": "development_descriptive_only_no_confirmatory_inference",
        })
    failures = [row for row in scored_rows if not row["complete_call_correct"]]
    report = {
        "schema_version": "1.0", "analysis_id": config["analysis_id"], "run_id": config["run_id"],
        "analysis_status": "development_offline_scoring_complete",
        "overall": overall, "failure_count": len(failures),
        "all_transport_accepted": all(row["transport_accepted"] for row in scored_rows),
        "tool_calls_executed": 0, "retries_executed": 0,
        "independent_validation_split_accessed": False,
        "confirmatory_inference_allowed": False, "cf05_status": "in_progress", "core_frozen": False,
        "interpretation": "single development run; observed differences are diagnostic and cannot test H3 or H4",
    }
    return {"scored_rows": scored_rows, "overall_report": report, "by_condition": by_condition,
            "by_method": by_method, "by_size": by_size,
            "by_condition_method_size": by_condition_method_size,
            "descriptive_contrasts": contrasts, "failure_rows": failures}


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    built = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a004_analysis_config_snapshot.json": config,
        "a004_scored_rows.json": {"schema_version": "1.0", "run_id": config["run_id"], "rows": built["scored_rows"]},
        "a004_overall_report.json": built["overall_report"],
        "a004_by_condition.json": built["by_condition"],
        "a004_by_method.json": built["by_method"],
        "a004_by_size.json": built["by_size"],
        "a004_by_condition_method_size.json": built["by_condition_method_size"],
        "a004_descriptive_contrasts.json": built["descriptive_contrasts"],
        "a004_failure_rows.json": built["failure_rows"],
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    rows = [{"filename": path.name, "sha256": file_hash(path), "bytes": path.stat().st_size}
            for path in sorted(output_dir.iterdir(), key=lambda item: item.name)]
    write_json(output_dir / "artifact_manifest.json", {"schema_version": "1.0", "analysis_id": config["analysis_id"],
               "artifact_count": len(rows), "artifacts": rows})
    return built["overall_report"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else WORKSPACE / args.output_dir
    print(json.dumps(build_outputs(output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
