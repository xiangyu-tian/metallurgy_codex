"""Offline scoring for the completed E3 multi-target mixed-pool R2 run."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Callable


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("multitarget_analysis_config_v1.json")


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
    if actual != binding["sha256"]:
        raise ValueError(f"bound file hash mismatch for {path}: {actual}")
    return path


def validate_config(config: dict[str, Any]) -> None:
    if config["run_id"] != "V11-CF05-E3-MULTITARGET-MIXED-R2-20260810":
        raise ValueError("unexpected run identity")
    if config["expected_result_count"] != 64 or config["expected_task_count"] != 8:
        raise ValueError("development grid changed")
    if config["methods"] != ["full_schema", "lexical_top5", "dense_top5", "hierarchical"]:
        raise ValueError("method set or order changed")
    if config["tool_pool_sizes"] != [17, 120]:
        raise ValueError("tool-pool size set changed")
    if not config["development_only"]:
        raise ValueError("analysis must remain development-only")
    if config["confirmatory_inference_allowed"] is not False or config["core_frozen"] is not False:
        raise ValueError("development analysis cannot become confirmatory or freeze the core")


def values_equal(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual is expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return float(actual) == float(expected)
    if isinstance(actual, dict) and isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            values_equal(actual[key], expected[key]) for key in actual
        )
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(
            values_equal(left, right) for left, right in zip(actual, expected)
        )
    return actual == expected


def parameters_compatible(actual: Any, expected: Any, schema: dict[str, Any]) -> bool:
    """Accept canonical inputs plus schema-declared optional values at their defaults."""
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        return False
    if not set(expected).issubset(actual):
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
        raise ValueError("cannot summarize an empty group")
    prompt_tokens = [(row.get("usage") or {}).get("prompt_tokens") for row in rows]
    completion_tokens = [(row.get("usage") or {}).get("completion_tokens") for row in rows]
    return {
        "cell_count": len(rows),
        "transport_acceptance_rate": mean(row["transport_accepted"] for row in rows),
        "single_tool_call_rate": mean(row["exactly_one_tool_call"] for row in rows),
        "acceptable_tool_selection_accuracy": mean(row["selection_correct"] for row in rows),
        "target_tool_selection_accuracy": mean(row["target_tool_selected"] for row in rows),
        "parameter_accuracy": mean(row["parameters_correct"] for row in rows),
        "complete_call_accuracy": mean(row["complete_call_correct"] for row in rows),
        "mean_api_latency_ms": mean(row["api_latency_ms"] for row in rows),
        "mean_prompt_tokens": mean(value for value in prompt_tokens if isinstance(value, int)),
        "mean_completion_tokens": mean(
            value for value in completion_tokens if isinstance(value, int)
        ),
    }


def group_summary(
    rows: list[dict[str, Any]],
    key_fn: Callable[[dict[str, Any]], tuple[Any, ...]],
    key_names: tuple[str, ...],
) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[key_fn(row)].append(row)
    return [
        {**dict(zip(key_names, key)), **summarize(group)}
        for key, group in sorted(groups.items())
    ]


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {name: validate_binding(binding) for name, binding in config["bindings"].items()}
    result_payload = load_json(paths["request_results"])
    runtime = load_json(paths["runtime_report"])
    scoring = load_json(paths["scoring_registry"])
    candidate_views = load_json(paths["candidate_views"])
    results = result_payload["results"]
    if result_payload["run_id"] != config["run_id"] or len(results) != 64:
        raise ValueError("request result identity or count changed")
    if len({row["cell_id"] for row in results}) != 64:
        raise ValueError("duplicate result cells")
    if Counter(row["method"] for row in results) != Counter({method: 16 for method in config["methods"]}):
        raise ValueError("method result grid incomplete")
    if Counter(row["tool_pool_size"] for row in results) != Counter({17: 32, 120: 32}):
        raise ValueError("tool-pool size result grid incomplete")
    expected_pairs = Counter(
        {(method, size): 8 for method in config["methods"] for size in config["tool_pool_sizes"]}
    )
    if Counter((row["method"], row["tool_pool_size"]) for row in results) != expected_pairs:
        raise ValueError("method-by-size result grid incomplete")
    if (
        runtime["external_api_calls"] != 64
        or runtime["transport_accepted_count"] != 64
        or runtime["provider_error_count"] != 0
        or runtime["tool_calls_executed"] != 0
        or runtime["retries_executed"] != 0
    ):
        raise ValueError("runtime report violates the frozen execution contract")
    gold_by_task = {row["task_id"]: row for row in scoring["tasks"]}
    if len(gold_by_task) != 8:
        raise ValueError("scoring registry task count changed")
    schemas_by_view: dict[str, dict[str, dict[str, Any]]] = {}
    for view in candidate_views["views"]:
        schemas_by_view[view["candidate_view_id"]] = {
            tool["function"]["name"]: tool["function"]["parameters"]
            for tool in view["openai_tools"]
        }
    scored_rows: list[dict[str, Any]] = []
    for row in results:
        gold = gold_by_task[row["task_id"]]
        visible_tools = set(row["selected_schema_tool_ids"])
        acceptable_visible = sorted(
            visible_tools.intersection(gold["acceptable_tools_full_candidate_scope"])
        )
        if gold["source_tool_id"] not in acceptable_visible:
            raise ValueError(f"source tool absent from submitted view: {row['cell_id']}")
        selected_tool_visible = row["selected_tool_id"] in visible_tools
        selection_correct = bool(
            row["transport_accepted"]
            and row["exactly_one_tool_call"]
            and selected_tool_visible
            and row["selected_tool_id"] in acceptable_visible
        )
        selected_schema = schemas_by_view.get(row["candidate_view_id"], {}).get(
            row["selected_tool_id"]
        )
        if not isinstance(selected_schema, dict):
            raise ValueError(f"selected tool schema unavailable: {row['cell_id']}")
        parameters_correct = bool(
            row["arguments_json_valid"]
            and parameters_compatible(
                row["arguments"], gold["expected_parameters"], selected_schema
            )
        )
        scored_rows.append(
            {
                "cell_id": row["cell_id"],
                "task_id": row["task_id"],
                "source_tool_id": gold["source_tool_id"],
                "pool_id": row["pool_id"],
                "pool_design": row["pool_design"],
                "tool_pool_size": row["tool_pool_size"],
                "method": row["method"],
                "candidate_view_id": row["candidate_view_id"],
                "transport_accepted": row["transport_accepted"],
                "exactly_one_tool_call": row["exactly_one_tool_call"],
                "selected_tool_id": row["selected_tool_id"],
                "selected_tool_visible": selected_tool_visible,
                "acceptable_tools_visible": acceptable_visible,
                "selection_correct": selection_correct,
                "target_tool_selected": row["selected_tool_id"] == gold["source_tool_id"],
                "arguments": row["arguments"],
                "expected_parameters": gold["expected_parameters"],
                "parameters_correct": parameters_correct,
                "complete_call_correct": selection_correct and parameters_correct,
                "api_latency_ms": row["api_latency_ms"],
                "usage": row["usage"],
                "tool_executed": row["tool_executed"],
                "retry_count": row["retry_count"],
            }
        )
    if not all(row["selected_tool_visible"] for row in scored_rows):
        raise ValueError("provider selected a tool outside the submitted schema")
    overall = summarize(scored_rows)
    by_method = group_summary(scored_rows, lambda row: (row["method"],), ("method",))
    by_method_size = group_summary(
        scored_rows,
        lambda row: (row["method"], row["tool_pool_size"]),
        ("method", "tool_pool_size"),
    )
    by_target = group_summary(
        scored_rows,
        lambda row: (row["source_tool_id"],),
        ("source_tool_id",),
    )
    by_target_method = group_summary(
        scored_rows,
        lambda row: (row["source_tool_id"], row["method"]),
        ("source_tool_id", "method"),
    )
    size_map = {(row["method"], row["tool_pool_size"]): row for row in by_method_size}
    descriptive_scale_effects = [
        {
            "method": method,
            "accuracy_17": size_map[(method, 17)]["acceptable_tool_selection_accuracy"],
            "accuracy_120": size_map[(method, 120)]["acceptable_tool_selection_accuracy"],
            "accuracy_120_minus_17": (
                size_map[(method, 120)]["acceptable_tool_selection_accuracy"]
                - size_map[(method, 17)]["acceptable_tool_selection_accuracy"]
            ),
            "interpretation": "development_descriptive_only_no_confirmatory_inference",
        }
        for method in config["methods"]
    ]
    ceiling = all(
        row[metric] == 1.0
        for row in by_method_size
        for metric in (
            "acceptable_tool_selection_accuracy",
            "target_tool_selection_accuracy",
            "parameter_accuracy",
            "complete_call_accuracy",
        )
    )
    report = {
        "schema_version": "1.0",
        "analysis_id": config["analysis_id"],
        "run_id": config["run_id"],
        "analysis_status": "development_analysis_complete",
        "result_count": len(scored_rows),
        "overall": overall,
        "by_method": by_method,
        "by_method_and_size": by_method_size,
        "by_target": by_target,
        "by_target_and_method": by_target_method,
        "descriptive_scale_effects": descriptive_scale_effects,
        "selected_tool_counts": dict(
            sorted(Counter(row["selected_tool_id"] for row in scored_rows).items())
        ),
        "ceiling_observed": ceiling,
        "conclusion": (
            "All four routing methods achieved perfect visible-acceptable selection and parameter accuracy "
            "at both 17 and 120 tools on this eight-task mixed-realistic development slice. The run validates "
            "multi-target execution and scoring, but the ceiling prevents method discrimination and does not "
            "support confirmatory H3/H4 inference."
            if ceiling
            else "The development slice produced method or scale differences that require descriptive review."
        ),
        "external_api_calls_added_by_analysis": 0,
        "tool_calls_executed": 0,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
    }
    return {"rows": scored_rows, "report": report}


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    built = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "multitarget_analysis_config_snapshot.json": config,
        "multitarget_scored_cells.json": {
            "schema_version": "1.0",
            "analysis_id": config["analysis_id"],
            "cell_count": len(built["rows"]),
            "rows": built["rows"],
        },
        "multitarget_development_analysis_report.json": built["report"],
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    rows = [
        {"filename": path.name, "sha256": file_hash(path), "bytes": path.stat().st_size}
        for path in sorted(output_dir.iterdir(), key=lambda item: item.name)
        if path.is_file() and path.name != "artifact_manifest.json"
    ]
    write_json(
        output_dir / "artifact_manifest.json",
        {
            "schema_version": "1.0",
            "analysis_id": config["analysis_id"],
            "artifact_count": len(rows),
            "artifacts": rows,
        },
    )
    return built["report"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else WORKSPACE / args.output_dir
    print(json.dumps(build_outputs(output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
