"""Materialize the no-call A003 four-method development execution opening."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "a003_routing_execution_opening_config_v1.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_binding(binding: dict[str, str]) -> Path:
    path = WORKSPACE / binding["path"]
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256_file(path)
    if actual != binding["sha256"].lower():
        raise ValueError(f"bound file hash mismatch for {path}: {actual}")
    return path


def validate_config(config: dict[str, Any]) -> None:
    if config["provider"] != "deepseek" or config["model"] != "deepseek-v4-flash":
        raise ValueError("provider or model changed")
    if config["openai_base_url"] != "https://api.deepseek.com":
        raise ValueError("OpenAI-compatible endpoint changed")
    if config["provider_max_attempts"] != 1 or config["timeout_seconds"] != 120:
        raise ValueError("transport attempt or timeout policy changed")
    if config["methods"] != [
        "full_schema",
        "lexical_top5",
        "dense_top5",
        "hierarchical",
    ]:
        raise ValueError("method set or order changed")
    if config["expected_cell_count"] != 96:
        raise ValueError("expected_cell_count must remain 96")
    if config["expected_method_cell_count"] != 24:
        raise ValueError("expected_method_cell_count must remain 24")
    if config["expected_top_k"] != 5:
        raise ValueError("expected_top_k must remain 5")
    if not config["request_blueprints_materialization_allowed"]:
        raise ValueError("request blueprint materialization must remain allowed")
    for field in (
        "external_api_calls_authorized",
        "external_data_sharing_authorized",
        "tool_execution_allowed",
        "confirmatory_inference_allowed",
        "independent_validation_split_access_allowed",
        "gold_visible_to_router",
        "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")


def _candidate_map(
    method: str,
    views_payload: dict[str, Any],
    readiness: dict[str, Any],
    expected_cells: set[str],
) -> dict[str, list[str]]:
    if views_payload["method"] != method:
        raise ValueError(f"candidate method mismatch: {method}")
    if views_payload["router_visible_gold"] is not False:
        raise ValueError(f"gold-visible candidate payload: {method}")
    if views_payload["external_api_calls"] != 0 or views_payload["tool_calls_executed"] != 0:
        raise ValueError(f"candidate payload already executed: {method}")
    if readiness["implementation_status"] != "candidate_implementation_passed_local_gate":
        raise ValueError(f"candidate local gate not passed: {method}")
    ready_key = f"ready_for_24_cell_{'hierarchical' if method == 'hierarchical' else method.replace('_top5', '')}_slice_generation"
    if readiness.get(ready_key) is not True:
        raise ValueError(f"candidate readiness flag missing: {method}")
    rows = views_payload["views"]
    if len(rows) != 24:
        raise ValueError(f"candidate view count changed: {method}")
    mapping = {}
    for row in rows:
        if row["cell_id"] not in expected_cells:
            raise ValueError(f"candidate cell outside frozen schedule: {row['cell_id']}")
        candidates = row["candidate_tool_ids"]
        if len(candidates) != 5 or len(set(candidates)) != 5:
            raise ValueError(f"candidate view is not a unique Top-5: {row['cell_id']}")
        mapping[row["cell_id"]] = candidates
    if set(mapping) != expected_cells:
        raise ValueError(f"candidate cell grid incomplete: {method}")
    return mapping


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {name: validate_binding(value) for name, value in config["bindings"].items()}
    tasks = load_json(paths["input_tasks"])
    pools = load_json(paths["selected_pools"])
    run_cells = load_json(paths["run_cells"])
    prompt = load_json(paths["selector_prompt"])
    schema_registry = load_json(paths["pool_schema_registry"])
    if run_cells["cell_count"] != config["expected_cell_count"]:
        raise ValueError("source run-cell count changed")
    cells = run_cells["cells"]
    cell_counts = Counter(row["method"] for row in cells)
    if cell_counts != Counter({method: 24 for method in config["methods"]}):
        raise ValueError(f"source method grid changed: {cell_counts}")
    task_by_id = {row["task_id"]: row for row in tasks["tasks"]}
    pool_by_id = {row["pool_id"]: row for row in pools["pools"]}
    schema_by_id = {row["tool_id"]: row["openai_tool"] for row in schema_registry["entries"]}

    candidate_maps: dict[str, dict[str, list[str]]] = {}
    for method, prefix in (
        ("lexical_top5", "lexical"),
        ("dense_top5", "dense"),
        ("hierarchical", "hierarchical"),
    ):
        method_cells = {row["cell_id"] for row in cells if row["method"] == method}
        candidate_maps[method] = _candidate_map(
            method,
            load_json(paths[f"{prefix}_views"]),
            load_json(paths[f"{prefix}_readiness"]),
            method_cells,
        )

    schema_views: dict[str, dict[str, Any]] = {}
    blueprints = []
    for cell in cells:
        pool = pool_by_id[cell["pool_id"]]
        if cell["method"] == "full_schema":
            selected_ids = list(pool["tool_order"])
        else:
            selected_ids = list(candidate_maps[cell["method"]][cell["cell_id"]])
        expected_count = pool["tool_pool_size"] if cell["method"] == "full_schema" else 5
        if len(selected_ids) != expected_count:
            raise ValueError(f"selector schema count mismatch: {cell['cell_id']}")
        if not set(selected_ids).issubset(pool["tool_order"]):
            raise ValueError(f"selected schema escaped pool: {cell['cell_id']}")
        tool_schemas = [schema_by_id[tool_id] for tool_id in selected_ids]
        schema_hash = json_hash(tool_schemas)
        schema_view_id = f"schema-{schema_hash[:16]}"
        existing = schema_views.get(schema_view_id)
        view = {
            "schema_view_id": schema_view_id,
            "schema_sha256": schema_hash,
            "tool_count": len(selected_ids),
            "tool_ids": selected_ids,
            "tools": tool_schemas,
        }
        if existing is not None and canonical_json(existing) != canonical_json(view):
            raise ValueError(f"schema view hash-prefix collision: {schema_view_id}")
        schema_views[schema_view_id] = view
        task = task_by_id[cell["task_id"]]
        request_body = {
            "model": config["model"],
            "messages": [
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": task["problem_text"]},
            ],
            "tools": tool_schemas,
            "tool_choice": config["tool_choice"],
            "temperature": config["temperature"],
            "max_tokens": config["max_tokens"],
            "stream": False,
            "thinking": {"type": config["thinking"]},
        }
        blueprints.append(
            {
                **cell,
                "schema_view_id": schema_view_id,
                "schema_view_sha256": schema_hash,
                "selected_tool_ids": selected_ids,
                "request_body_sha256": json_hash(request_body),
                "request_body_materialization": {
                    "model": config["model"],
                    "system_prompt_sha256": hashlib.sha256(
                        prompt["system"].encode("utf-8")
                    ).hexdigest(),
                    "user_problem_text": task["problem_text"],
                    "schema_view_id": schema_view_id,
                    "tool_choice": config["tool_choice"],
                    "temperature": config["temperature"],
                    "max_tokens": config["max_tokens"],
                    "stream": False,
                    "thinking": {"type": config["thinking"]},
                },
                "adapter_settings": {"thinking": config["thinking"]},
                "execution_status": "not_executed_pending_explicit_authorization",
            }
        )

    forbidden = tuple(prompt["gold_fields_forbidden"])
    router_material = canonical_json({"schema_views": schema_views, "blueprints": blueprints})
    gold_absent = all(f'"{field}"' not in router_material for field in forbidden)
    if not gold_absent:
        raise ValueError("gold field leaked into execution opening")
    api_key_absent = "api_key" not in router_material.casefold()
    if not api_key_absent:
        raise ValueError("API key material leaked into execution opening")
    schema_view_payload = {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "view_count": len(schema_views),
        "views": [schema_views[key] for key in sorted(schema_views)],
    }
    blueprint_payload = {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "development_only": True,
        "request_blueprints_materialized": True,
        "external_api_calls": 0,
        "tool_calls_executed": 0,
        "cell_count": len(blueprints),
        "materialization_contract": (
            "messages=system prompt plus user_problem_text; tools=schema view tools; "
            "all other API request fields are copied from request_body_materialization; "
            "adapter_settings independently validate the same frozen thinking mode"
        ),
        "cells": blueprints,
    }
    method_rows = []
    for method in config["methods"]:
        method_blueprints = [row for row in blueprints if row["method"] == method]
        method_rows.append(
            {
                "method": method,
                "cell_count": len(method_blueprints),
                "schema_counts": sorted({len(row["selected_tool_ids"]) for row in method_blueprints}),
                "candidate_source": (
                    "bound_pool_full_schema" if method == "full_schema" else "hash_bound_candidate_views"
                ),
                "ready": len(method_blueprints) == 24,
            }
        )
    preflight = {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "opening_status": "prepared_eligible_pending_explicit_authorization",
        "checks": {
            "all_bound_hashes_valid": True,
            "all_four_methods_ready": all(row["ready"] for row in method_rows),
            "exact_96_request_blueprints": len(blueprints) == 96,
            "exact_24_cells_per_method": all(row["cell_count"] == 24 for row in method_rows),
            "full_schema_counts_are_17_or_120": next(
                row for row in method_rows if row["method"] == "full_schema"
            )["schema_counts"] == [17, 120],
            "top5_methods_have_exactly_5_schemas": all(
                row["schema_counts"] == [5]
                for row in method_rows
                if row["method"] != "full_schema"
            ),
            "all_selected_tools_within_bound_pool": True,
            "gold_fields_absent": gold_absent,
            "api_key_absent": api_key_absent,
            "external_api_calls_zero": True,
            "tool_execution_zero": True,
        },
        "methods": method_rows,
        "schema_view_count": len(schema_views),
        "external_api_calls": 0,
        "tool_calls_executed": 0,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
    }
    if not all(preflight["checks"].values()):
        raise ValueError("execution-opening preflight failed")
    authorization_request = {
        "schema_version": "1.0",
        "opening_id": config["opening_id"],
        "decision": "pending_user_authorization",
        "eligible_for_external_execution_authorization": True,
        "external_data_sharing_authorized": False,
        "external_api_execution_authorized": False,
        "tool_execution_allowed": False,
        "proposed_external_scope": {
            "provider": config["provider"],
            "model": config["model"],
            "request_count": len(blueprints),
            "content": "two development task texts and the bound schema views referenced by 96 cells",
            "independent_validation_split_included": False,
            "metallurgy_tool_execution": False,
        },
        "required_authorization": (
            "explicitly approve sending the frozen A003 development task texts and schema views "
            "to the configured DeepSeek API for one non-confirmatory selector run"
        ),
    }
    return {
        "schema_views": schema_view_payload,
        "blueprints": blueprint_payload,
        "preflight": preflight,
        "authorization_request": authorization_request,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    authorization_path = HERE / config["execution_authorization_file"]
    if authorization_path.exists():
        raise ValueError("unexpected A003 routing execution authorization file")
    built = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a003_routing_execution_config_snapshot.json": config,
        "a003_routing_schema_views.json": built["schema_views"],
        "a003_routing_request_blueprints.json": built["blueprints"],
        "a003_routing_execution_preflight.json": built["preflight"],
        "execution_authorization_request.json": built["authorization_request"],
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    artifact_rows = [
        {"filename": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
        for path in sorted(output_dir.iterdir(), key=lambda item: item.name)
        if path.is_file() and path.name != "artifact_manifest.json"
    ]
    write_json(
        output_dir / "artifact_manifest.json",
        {
            "schema_version": "1.0",
            "opening_id": config["opening_id"],
            "artifact_count": len(artifact_rows),
            "artifacts": artifact_rows,
        },
    )
    return built["preflight"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = WORKSPACE / output_dir
    print(json.dumps(build_outputs(output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
