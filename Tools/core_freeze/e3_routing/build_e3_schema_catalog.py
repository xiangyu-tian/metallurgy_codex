"""Build the candidate 120-entry E3 routing catalog without external calls.

The output deliberately distinguishes verified executable tools, implemented but
unverified tools, and planned schema-only entries.  Planned schemas are suitable
for API-size feasibility checks only; they are not parameter contracts and may
not be presented as executable engines or formal E3 targets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict, deque
from copy import deepcopy
from pathlib import Path
from typing import Any

WORKSPACE = Path(__file__).resolve().parents[3]
TOOLS_DIR = WORKSPACE / "Tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from models_core import ModelRegistry  # noqa: E402
from models_core.llm_adapters import model_tools  # noqa: E402


CONFIG_PATH = Path(__file__).with_name("catalog_config_v1_candidate.json")
FUNCTION_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validate_bound_source(path: Path, expected_hash: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256_file(path)
    if actual != expected_hash.lower():
        raise ValueError(f"source hash mismatch for {path}: {actual}")


def lifecycle_status(source: dict[str, Any], verified_ids: set[str]) -> str:
    tool_id = source["model_id"]
    if tool_id in verified_ids:
        return "verified_executable_core"
    if source["implementation_status"] == "implemented_tested_unreviewed":
        return "implemented_tested_unreviewed"
    return "schema_only_planned"


def public_description(source: dict[str, Any]) -> str:
    parts = [
        source["tool_name"],
        f"功能：{source['core_method']}",
        f"输入：{source['main_input']}",
        f"输出：{source['main_output']}",
        f"适用边界：{source['applicable_boundary_risk']}",
    ]
    return "；".join(parts)[:1024]


def planned_parameters(source: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    field = config["planned_schema_required_field"]
    return {
        "type": "object",
        "properties": {
            field: {
                "type": "string",
                "description": f"按候选目录摘要提供输入：{source['main_input']}",
            },
            "context": {
                "type": "object",
                "description": "可选上下文；字段尚未形成可执行参数契约。",
                "properties": {},
            },
        },
        "required": [field],
        "additionalProperties": False,
    }


def validate_openai_tool(tool: dict[str, Any]) -> None:
    if tool.get("type") != "function":
        raise ValueError("tool type must be function")
    function = tool.get("function", {})
    name = function.get("name", "")
    if not FUNCTION_NAME.fullmatch(name):
        raise ValueError(f"invalid function name: {name!r}")
    if not isinstance(function.get("description"), str):
        raise ValueError(f"missing description: {name}")
    if len(function["description"]) > 1024:
        raise ValueError(f"description too long: {name}")
    parameters = function.get("parameters", {})
    if parameters.get("type") != "object":
        raise ValueError(f"parameters must be object: {name}")
    properties = parameters.get("properties")
    required = parameters.get("required", [])
    if not isinstance(properties, dict) or not isinstance(required, list):
        raise ValueError(f"invalid properties/required: {name}")
    if not set(required).issubset(properties):
        raise ValueError(f"required field absent from properties: {name}")


def expanded_order(planned: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Priority blocks with deterministic round-robin scenario coverage."""
    result: list[dict[str, Any]] = []
    for priority in sorted(
        {row["priority"] for row in planned},
        key=lambda item: (PRIORITY_ORDER.get(item, 99), item),
    ):
        block = [row for row in planned if row["priority"] == priority]
        scenario_order = list(dict.fromkeys(row["scenario"] for row in block))
        queues: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
        for row in sorted(block, key=lambda item: item["source_row"]):
            queues[row["scenario"]].append(row)
        while any(queues[scenario] for scenario in scenario_order):
            for scenario in scenario_order:
                if queues[scenario]:
                    result.append(queues[scenario].popleft())
    return result


def build_catalog(config: dict[str, Any]) -> dict[str, Any]:
    inventory_path = WORKSPACE / config["source_inventory_path"]
    contracts_path = WORKSPACE / config["verified_contracts_path"]
    validate_bound_source(inventory_path, config["source_inventory_sha256"])
    validate_bound_source(contracts_path, config["verified_contracts_sha256"])

    inventory = load_json(inventory_path)
    source_tools = inventory["tools"]
    if len(source_tools) != 120:
        raise ValueError(f"expected 120 source rows, got {len(source_tools)}")
    source_by_id = {row["model_id"]: row for row in source_tools}
    if len(source_by_id) != 120:
        raise ValueError("source tool IDs are not unique")

    contracts = load_json(contracts_path)["contracts"]
    verified_ids = {contract["tool_id"] for contract in contracts}
    registry = ModelRegistry()
    registry.discover()
    runtime_cards = registry.list_models()
    runtime_ids = {card["model_code"] for card in runtime_cards}
    implemented_ids = {
        row["model_id"]
        for row in source_tools
        if row["implementation_status"] == "implemented_tested_unreviewed"
    }
    if runtime_ids != implemented_ids or len(runtime_ids) != 17:
        raise ValueError("runtime registry does not match the 17 implemented source rows")
    if not verified_ids.issubset(runtime_ids):
        raise ValueError("verified_core contains a non-runtime tool")

    runtime_definitions = {
        item["function"]["name"]: item for item in model_tools(registry)
    }
    entries = []
    for source in sorted(source_tools, key=lambda row: row["source_row"]):
        tool_id = source["model_id"]
        status = lifecycle_status(source, verified_ids)
        if tool_id in runtime_definitions:
            openai_tool = deepcopy(runtime_definitions[tool_id])
            openai_tool["function"]["description"] = public_description(source)
            fidelity = "runtime_parameter_schema"
        else:
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool_id,
                    "description": public_description(source),
                    "parameters": planned_parameters(source, config),
                },
            }
            fidelity = config["planned_schema_fidelity"]
        validate_openai_tool(openai_tool)
        entries.append(
            {
                "tool_id": tool_id,
                "semantic_alias": source["api_name"],
                "tool_name": source["tool_name"],
                "scenario": source["scenario"],
                "tool_type": source["tool_type"],
                "core_method": source["core_method"],
                "main_input": source["main_input"],
                "main_output": source["main_output"],
                "applicable_boundary_risk": source["applicable_boundary_risk"],
                "priority": source["priority"],
                "source_row": source["source_row"],
                "lifecycle_status": status,
                "schema_fidelity": fidelity,
                "formal_execution_allowed": tool_id in verified_ids,
                "formal_target_allowed": tool_id in verified_ids,
                "family_review_status": source["independence_precheck"],
                "family_group_id": source.get("family_group_id"),
                "api_visible_lifecycle_label": False,
                "openai_tool": openai_tool,
            }
        )

    entry_by_id = {entry["tool_id"]: entry for entry in entries}
    base_ids = [
        row["model_id"]
        for row in sorted(source_tools, key=lambda item: item["source_row"])
        if row["model_id"] in runtime_ids
    ]
    planned = [row for row in source_tools if row["model_id"] not in runtime_ids]
    ordered_ids = base_ids + [row["model_id"] for row in expanded_order(planned)]
    if len(ordered_ids) != 120 or len(set(ordered_ids)) != 120:
        raise ValueError("pool ordering must contain 120 unique IDs")

    pools = []
    previous: set[str] = set()
    for size in config["pool_sizes"]:
        ids = ordered_ids[:size]
        current = set(ids)
        if not previous.issubset(current) or len(ids) != size:
            raise ValueError(f"pool nesting failed at size {size}")
        statuses = Counter(entry_by_id[tool_id]["lifecycle_status"] for tool_id in ids)
        pools.append(
            {
                "pool_id": f"E3-BASE-POOL-{size}-CANDIDATE-V1",
                "tool_count": size,
                "tool_ids": ids,
                "lifecycle_counts": dict(sorted(statuses.items())),
                "verified_target_count": sum(
                    entry_by_id[tool_id]["formal_target_allowed"] for tool_id in ids
                ),
                "nested_parent_size": None if not previous else len(previous),
            }
        )
        previous = current

    return {
        "catalog": {
            "schema_version": "1.0",
            "candidate_id": config["candidate_id"],
            "protocol_version": config["protocol_version"],
            "entry_count": len(entries),
            "verified_executable_count": len(verified_ids),
            "implemented_unverified_count": len(runtime_ids - verified_ids),
            "schema_only_planned_count": len(entries) - len(runtime_ids),
            "api_visible_lifecycle_labels": config["api_visible_lifecycle_labels"],
            "formal_use_status": config["formal_use_status"],
            "entries": entries,
        },
        "pools": {
            "schema_version": "1.0",
            "candidate_id": config["candidate_id"],
            "ordering_policy": config["expansion_policy"],
            "pool_relation": "Pool-17 subset Pool-50 subset Pool-100 subset Pool-120",
            "formal_use_status": config["formal_use_status"],
            "pools": pools,
        },
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    built = build_catalog(config)
    output_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = output_dir / "e3_schema_catalog_v1_candidate.json"
    pools_path = output_dir / "e3_nested_pool_manifest_v1_candidate.json"
    config_snapshot = output_dir / "catalog_config_snapshot.json"
    write_json(catalog_path, built["catalog"])
    write_json(pools_path, built["pools"])
    write_json(config_snapshot, config)

    entries = {entry["tool_id"]: entry for entry in built["catalog"]["entries"]}
    pool_files = []
    for pool in built["pools"]["pools"]:
        path = output_dir / f"openai_tools_pool_{pool['tool_count']}.json"
        write_json(path, [entries[tool_id]["openai_tool"] for tool_id in pool["tool_ids"]])
        pool_files.append(path)

    unresolved = sum(
        entry["family_review_status"] == "needs_family_review"
        for entry in built["catalog"]["entries"]
    )
    report = {
        "candidate_id": config["candidate_id"],
        "status": "candidate_generated_not_formally_eligible",
        "catalog_entry_count": 120,
        "runtime_implemented_count": 17,
        "verified_executable_count": 5,
        "schema_only_planned_count": 103,
        "unresolved_family_review_entry_count": unresolved,
        "pool_sizes": config["pool_sizes"],
        "nested_pool_check": True,
        "external_api_calls": 0,
        "external_api_calls_authorized": False,
        "formal_execution_scope": "verified_core_only",
        "planned_schema_limit": (
            "103 planned entries use summary stubs for routing/API feasibility; "
            "they are not executable parameter contracts"
        ),
        "blocking_requirements": [
            "resolve CF-05 family independence reviews",
            "freeze target-specific 0/4/8 contract-neighbor pools",
            "freeze parameter contracts before formal E3 parameter scoring",
            "obtain separate authorization before CF-06 external API feasibility calls",
        ],
    }
    report_path = output_dir / "build_report.json"
    write_json(report_path, report)

    artifact_paths = [catalog_path, pools_path, config_snapshot, report_path, *pool_files]
    manifest = {
        "candidate_id": config["candidate_id"],
        "artifact_count": len(artifact_paths),
        "artifacts": [
            {
                "filename": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in sorted(artifact_paths, key=lambda item: item.name)
        ],
    }
    write_json(output_dir / "artifact_manifest.json", manifest)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    report = build_outputs(Path(args.output_dir).resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
