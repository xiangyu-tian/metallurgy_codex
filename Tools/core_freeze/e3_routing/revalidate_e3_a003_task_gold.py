"""Recompute A003 task-level acceptable tools from frozen numeric tolerances."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import sys
from pathlib import Path
from typing import Any, Callable


WORKSPACE = Path(__file__).resolve().parents[3]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from Tools.core_freeze.e3_routing.candidate_runtime_adapters import invoke  # noqa: E402


CONFIG_PATH = Path(__file__).with_name("a003_task_gold_revalidation_config_v1.json")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


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


def nested(value: dict[str, Any], path: list[str]) -> Any:
    current: Any = value
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def primary_check(task: dict[str, Any]) -> dict[str, float]:
    checks = task["scoring_rule"]["checks"]
    if len(checks) != 1 or checks[0].get("path") != "molar_mass":
        raise ValueError(f"unexpected A003 scoring contract: {task['task_id']}")
    check = checks[0]
    if check.get("op") != "approx":
        raise ValueError(f"A003 scoring rule must be approx: {task['task_id']}")
    return {
        "expected": float(check["value"]),
        "abs_tol": float(check.get("abs_tol", 0.0)),
        "rel_tol": float(check.get("rel_tol", 0.0)),
    }


def validate_environment(sources: dict[str, Any]) -> dict[str, Any]:
    frozen = sources["candidate_environment_verification"]
    expected = frozen["top_level_versions"]["pymatgen"]
    try:
        actual = importlib.metadata.version("pymatgen")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError(
            "pymatgen is missing; run this revalidation with the locked "
            ".venv-e3-candidates interpreter"
        ) from exc
    if actual != expected:
        raise RuntimeError(f"pymatgen version mismatch: expected {expected}, got {actual}")
    return {
        "python_version": sys.version.split()[0],
        "pymatgen_expected_version": expected,
        "pymatgen_actual_version": actual,
        "environment_match": True,
    }


def evaluate_candidate(
    task: dict[str, Any],
    tool_id: str,
    config: dict[str, Any],
    invoke_fn: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    policy = config["direct_acceptance_policy"]
    params = dict(task["canonical_inputs"])
    if sorted(params) != sorted(policy["required_input_keys"]):
        raise ValueError(f"task input contract changed: {task['task_id']}")
    execution = invoke_fn(tool_id, params)
    value = nested(execution, policy["result_value_path"])
    unit = nested(execution, policy["result_unit_path"])
    check = primary_check(task)
    numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
    finite = numeric and math.isfinite(float(value))
    tolerance = check["abs_tol"] + check["rel_tol"] * abs(check["expected"])
    delta = abs(float(value) - check["expected"]) if finite else None
    acceptable = (
        execution.get("success") is True
        and finite
        and unit == policy["required_unit"]
        and delta is not None
        and delta <= tolerance
    )
    return {
        "candidate_tool_id": tool_id,
        "input": params,
        "execution": execution,
        "expected_molar_mass": check["expected"],
        "absolute_tolerance": check["abs_tol"],
        "relative_tolerance": check["rel_tol"],
        "effective_tolerance": tolerance,
        "candidate_molar_mass": float(value) if finite else None,
        "absolute_error": delta,
        "unit_matches": unit == policy["required_unit"],
        "directly_acceptable": acceptable,
    }


def build(
    config: dict[str, Any],
    *,
    invoke_fn: Callable[[str, dict[str, Any]], dict[str, Any]] = invoke,
    validate_runtime_environment: bool = True,
) -> dict[str, Any]:
    if config.get("confirmatory_use_allowed") is not False:
        raise ValueError("confirmatory_use_allowed must remain false")
    if config.get("external_api_calls_authorized") is not False:
        raise ValueError("external_api_calls_authorized must remain false")
    if config.get("core_frozen") is not False:
        raise ValueError("core_frozen must remain false")
    if config.get("derived_or_multi_step_tools_primary_acceptable") is not False:
        raise ValueError("derived tools cannot silently enter the primary estimand")
    if config.get("alternative_success_must_be_reported") is not True:
        raise ValueError("alternative success reporting must remain enabled")

    paths = {name: validate_binding(binding) for name, binding in config["bindings"].items()}
    sources = {
        name: load_json(path)
        for name, path in paths.items()
        if path.suffix.lower() == ".json"
    }
    review = sources["independent_review_report"]
    if review.get("status") != "pool_and_relation_review_passed_task_gold_revalidation_required":
        raise ValueError("independent review status does not permit task revalidation")
    environment = (
        validate_environment(sources)
        if validate_runtime_environment
        else {"environment_match": "test_injection"}
    )

    registry = sources["candidate_registry_batch1"]
    registered = {row["candidate_tool_id"]: row for row in registry["candidates"]}
    for tool_id in config["direct_candidate_tool_ids"]:
        row = registered.get(tool_id)
        if row is None:
            raise ValueError(f"direct candidate is not registered: {tool_id}")
        required = row["openai_tool"]["function"]["parameters"].get("required", [])
        if required != config["direct_acceptance_policy"]["required_input_keys"]:
            raise ValueError(f"direct candidate input contract changed: {tool_id}")

    tasks = [
        row
        for row in sources["a003_taskset"]["tasks"]
        if row.get("source_tool_id") == config["target_tool_id"]
    ]
    rows = []
    execution_rows = []
    for task in tasks:
        accepted = [config["target_tool_id"]]
        evaluations = []
        for tool_id in config["direct_candidate_tool_ids"]:
            evaluation = evaluate_candidate(task, tool_id, config, invoke_fn)
            evaluations.append(evaluation)
            execution_rows.append({"task_id": task["task_id"], **evaluation})
            if evaluation["directly_acceptable"]:
                accepted.append(tool_id)
        rows.append(
            {
                "task_id": task["task_id"],
                "target_tool_id": config["target_tool_id"],
                "problem_text": task["problem_text"],
                "canonical_inputs": task["canonical_inputs"],
                "scoring_rule": task["scoring_rule"],
                "original_acceptable_tools": task["acceptable_tools"],
                "revalidated_primary_acceptable_tools": accepted,
                "direct_candidate_evaluations": evaluations,
                "derived_or_multi_step_tools_primary_acceptable": False,
                "derived_or_multi_step_neighbor_ids": config[
                    "derived_or_multi_step_neighbor_ids"
                ],
                "alternative_success_must_be_reported": True,
            }
        )

    accepted_count = sum(
        config["direct_candidate_tool_ids"][0]
        in row["revalidated_primary_acceptable_tools"]
        for row in rows
    )
    report = {
        "revalidation_id": config["revalidation_id"],
        "status": "task_level_primary_acceptable_sets_revalidated_development_ready",
        "target_tool_id": config["target_tool_id"],
        "selection_estimand": config["selection_estimand"],
        "task_count": len(rows),
        "direct_candidate_tool_count": len(config["direct_candidate_tool_ids"]),
        "direct_candidate_acceptance_count": accepted_count,
        "singleton_acceptable_set_count": sum(
            len(row["revalidated_primary_acceptable_tools"]) == 1 for row in rows
        ),
        "multiple_acceptable_set_count": sum(
            len(row["revalidated_primary_acceptable_tools"]) > 1 for row in rows
        ),
        "derived_or_multi_step_tools_primary_acceptable": False,
        "alternative_success_must_be_reported": True,
        "environment": environment,
        "development_routing_run_allowed": config[
            "development_routing_run_allowed_after_pass"
        ],
        "confirmatory_use_allowed": False,
        "external_api_calls": 0,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "next_gate": "build a hash-bound A003 development routing opening package using the revalidated task registry",
    }
    return {"report": report, "task_rows": rows, "execution_rows": execution_rows}


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    result = build(config)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "a003_task_gold_revalidation_config_snapshot.json": config,
        "a003_task_gold_revalidation_report.json": result["report"],
        "a003_task_acceptable_tools_registry.json": {"tasks": result["task_rows"]},
        "a003_direct_candidate_execution_results.json": {"rows": result["execution_rows"]},
    }
    paths = []
    for filename, value in artifacts.items():
        path = output_dir / filename
        write_json(path, value)
        paths.append(path)
    manifest = {
        "revalidation_id": config["revalidation_id"],
        "artifact_count": len(paths),
        "artifacts": [
            {
                "filename": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in sorted(paths)
        ],
    }
    write_json(output_dir / "artifact_manifest.json", manifest)
    return result["report"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    report = build_outputs(args.output_dir.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
