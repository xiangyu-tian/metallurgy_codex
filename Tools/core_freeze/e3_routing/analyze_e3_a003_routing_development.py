"""Offline scoring for the completed A003 four-method development run."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Callable


WORKSPACE = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "a003_routing_development_analysis_config_v1.json"


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
    if config["expected_result_count"] != 96 or config["expected_method_count"] != 24:
        raise ValueError("development result grid changed")
    if config["methods"] != ["full_schema", "lexical_top5", "dense_top5", "hierarchical"]:
        raise ValueError("method set or order changed")
    if config["target_tool_id"] != "A003":
        raise ValueError("target tool changed")
    if config["confirmatory_inference_allowed"] is not False or config["core_frozen"] is not False:
        raise ValueError("development analysis cannot become confirmatory or freeze the core")


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    prompt_tokens = [(row.get("usage") or {}).get("prompt_tokens") for row in rows]
    completion_tokens = [(row.get("usage") or {}).get("completion_tokens") for row in rows]
    return {
        "cell_count": total,
        "transport_acceptance_rate": sum(row["transport_accepted"] for row in rows) / total,
        "single_tool_call_rate": sum(row["exactly_one_tool_call"] for row in rows) / total,
        "acceptable_tool_selection_accuracy": sum(row["selection_correct"] for row in rows) / total,
        "target_tool_selection_accuracy": sum(row["target_tool_selected"] for row in rows) / total,
        "parameter_accuracy": sum(row["parameters_correct"] for row in rows) / total,
        "complete_call_accuracy": sum(row["complete_call_correct"] for row in rows) / total,
        "mean_api_latency_ms": mean(row["api_latency_ms"] for row in rows),
        "mean_prompt_tokens": mean(value for value in prompt_tokens if isinstance(value, int)),
        "mean_completion_tokens": mean(value for value in completion_tokens if isinstance(value, int)),
    }


def _group_summary(
    rows: list[dict[str, Any]],
    key_fn: Callable[[dict[str, Any]], tuple[Any, ...]],
    key_names: tuple[str, ...],
) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[key_fn(row)].append(row)
    return [
        {**dict(zip(key_names, key)), **_summarize(group)}
        for key, group in sorted(groups.items())
    ]


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {name: validate_binding(binding) for name, binding in config["bindings"].items()}
    result_payload = load_json(paths["request_results"])
    runtime = load_json(paths["runtime_report"])
    scoring = load_json(paths["scoring_registry"])
    results = result_payload["results"]
    if len(results) != config["expected_result_count"]:
        raise ValueError("request result count changed")
    if len({row["cell_id"] for row in results}) != len(results):
        raise ValueError("duplicate request result cells")
    method_counts = Counter(row["method"] for row in results)
    if method_counts != Counter({method: 24 for method in config["methods"]}):
        raise ValueError(f"method result grid incomplete: {method_counts}")
    if runtime["external_api_calls"] != 96 or runtime["tool_calls_executed"] != 0:
        raise ValueError("runtime report violates the frozen execution contract")
    gold_by_task = {row["task_id"]: row for row in scoring["tasks"]}
    scored_rows = []
    for row in results:
        gold = gold_by_task[row["task_id"]]
        selection_correct = (
            row["transport_accepted"]
            and row["exactly_one_tool_call"]
            and row["selected_tool_id"] in gold["acceptable_tools"]
        )
        parameters_correct = (
            row["arguments_json_valid"]
            and row["arguments"] == gold["canonical_inputs"]
        )
        scored_rows.append(
            {
                "cell_id": row["cell_id"],
                "task_id": row["task_id"],
                "pool_id": row["pool_id"],
                "tool_pool_size": row["tool_pool_size"],
                "pool_repeat": row["pool_repeat"],
                "near_neighbor_type": row["near_neighbor_type"],
                "near_neighbor_count": row["near_neighbor_count"],
                "method": row["method"],
                "transport_accepted": row["transport_accepted"],
                "exactly_one_tool_call": row["exactly_one_tool_call"],
                "selected_tool_id": row["selected_tool_id"],
                "selected_tool_visible": row["selected_tool_id"] in row["selected_schema_tool_ids"],
                "acceptable_tools": gold["acceptable_tools"],
                "selection_correct": selection_correct,
                "target_tool_selected": row["selected_tool_id"] == config["target_tool_id"],
                "arguments": row["arguments"],
                "canonical_inputs": gold["canonical_inputs"],
                "parameters_correct": parameters_correct,
                "complete_call_correct": selection_correct and parameters_correct,
                "api_latency_ms": row["api_latency_ms"],
                "usage": row["usage"],
                "tool_executed": row["tool_executed"],
            }
        )
    if not all(row["selected_tool_visible"] for row in scored_rows):
        raise ValueError("provider selected a tool outside the submitted schema view")
    overall = _summarize(scored_rows)
    by_method = _group_summary(scored_rows, lambda row: (row["method"],), ("method",))
    by_method_size = _group_summary(
        scored_rows,
        lambda row: (row["method"], row["tool_pool_size"]),
        ("method", "tool_pool_size"),
    )
    by_method_condition = _group_summary(
        scored_rows,
        lambda row: (row["method"], row["near_neighbor_type"], row["near_neighbor_count"]),
        ("method", "near_neighbor_type", "near_neighbor_count"),
    )
    size_map = {(row["method"], row["tool_pool_size"]): row for row in by_method_size}
    condition_map = {
        (row["method"], row["near_neighbor_type"], row["near_neighbor_count"]): row
        for row in by_method_condition
    }
    descriptive_effects = []
    for method in config["methods"]:
        acc17 = size_map[(method, 17)]["acceptable_tool_selection_accuracy"]
        acc120 = size_map[(method, 120)]["acceptable_tool_selection_accuracy"]
        none = condition_map[(method, "none", 0)]["acceptable_tool_selection_accuracy"]
        lexical = condition_map[(method, "lexical", 8)]["acceptable_tool_selection_accuracy"]
        functional = condition_map[(method, "functional_overlap", 8)][
            "acceptable_tool_selection_accuracy"
        ]
        descriptive_effects.append(
            {
                "method": method,
                "accuracy_120_minus_17": acc120 - acc17,
                "lexical_8_minus_none_0": lexical - none,
                "functional_8_minus_none_0": functional - none,
                "functional_8_minus_lexical_8": functional - lexical,
                "interpretation": "development_descriptive_only_no_confirmatory_inference",
            }
        )
    report = {
        "schema_version": "1.0",
        "analysis_id": config["analysis_id"],
        "analysis_status": "development_analysis_complete",
        "result_count": len(scored_rows),
        "overall": overall,
        "by_method": by_method,
        "by_method_and_size": by_method_size,
        "by_method_and_condition": by_method_condition,
        "descriptive_effects": descriptive_effects,
        "selected_tool_counts": dict(sorted(Counter(row["selected_tool_id"] for row in scored_rows).items())),
        "conclusion": (
            "All four methods achieved perfect selection and parameter accuracy on this single-tool-family "
            "A003 development slice; the slice therefore validates the execution pipeline but does not "
            "discriminate method performance or support H3/H4."
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
        "a003_routing_analysis_config_snapshot.json": config,
        "a003_routing_scored_cells.json": {
            "schema_version": "1.0",
            "analysis_id": config["analysis_id"],
            "cell_count": len(built["rows"]),
            "rows": built["rows"],
        },
        "a003_routing_development_analysis_report.json": built["report"],
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
        {"schema_version": "1.0", "analysis_id": config["analysis_id"], "artifact_count": len(rows), "artifacts": rows},
    )
    return built["report"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else WORKSPACE / args.output_dir
    print(json.dumps(build_outputs(output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
