"""Revalidate direct alternative tools for the four non-A003 E3 targets.

This is development evidence, not a claim that every entry in the 137-schema
registry has received expert review.  Candidate outputs are compared with the
frozen, independently generated task checks.
"""

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


CONFIG_PATH = Path(__file__).with_name("multitarget_task_gold_config_v1.json")


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


def nested(value: Any, dotted_path: str) -> Any:
    current = value
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def equal_value(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and set(actual) == set(expected)
            and all(equal_value(actual[key], expected[key]) for key in expected)
        )
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and math.isfinite(float(actual))
            and float(actual) == float(expected)
        )
    return actual == expected


def score_projected_output(task: dict[str, Any], projected: dict[str, Any]) -> dict[str, Any]:
    check_rows = []
    for check in task["scoring_rule"]["checks"]:
        actual = nested(projected, check["path"])
        if check["op"] == "equal":
            passed = equal_value(actual, check["value"])
            absolute_error = None
            effective_tolerance = None
        elif check["op"] == "approx":
            numeric = (
                isinstance(actual, (int, float))
                and not isinstance(actual, bool)
                and math.isfinite(float(actual))
            )
            expected = float(check["value"])
            absolute_error = abs(float(actual) - expected) if numeric else None
            effective_tolerance = float(check.get("abs_tol", 0.0)) + float(
                check.get("rel_tol", 0.0)
            ) * abs(expected)
            passed = (
                absolute_error is not None
                and absolute_error <= effective_tolerance
            )
        else:
            raise ValueError(f"unsupported scoring operation: {check['op']}")
        check_rows.append(
            {
                "path": check["path"],
                "op": check["op"],
                "expected": check["value"],
                "actual": actual,
                "absolute_error": absolute_error,
                "effective_tolerance": effective_tolerance,
                "passed": passed,
            }
        )
    return {"passed": all(row["passed"] for row in check_rows), "checks": check_rows}


def validate_environment(sources: dict[str, Any]) -> dict[str, Any]:
    expected = sources["candidate_environment_verification"]["top_level_versions"]
    required = {name: expected[name] for name in ("pint", "pymatgen")}
    actual = {}
    for package, version in required.items():
        try:
            actual[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as exc:
            raise RuntimeError(
                f"{package} is missing; use the locked E3 candidate environment"
            ) from exc
        if actual[package] != version:
            raise RuntimeError(
                f"{package} version mismatch: expected {version}, got {actual[package]}"
            )
    return {
        "python_version": sys.version.split()[0],
        "expected_versions": required,
        "actual_versions": actual,
        "environment_match": True,
    }


def candidate_scope_ids(
    target_id: str,
    neighbor_matrix: dict[str, Any],
    relation_registry: dict[str, Any],
) -> set[str]:
    target_row = next(
        row for row in neighbor_matrix["targets"] if row["target_tool_id"] == target_id
    )
    base_lexical = {
        row["candidate_tool_id"] for row in target_row["lexical_candidates"]
    }
    registered_relations = {
        row["candidate_tool_id"]
        for row in relation_registry["relations"]
        if row["target_tool_id"] == target_id
    }
    return base_lexical | registered_relations


def evaluate_candidate(
    task: dict[str, Any],
    tool_id: str,
    projection: dict[str, str],
    invoke_fn: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    execution = invoke_fn(tool_id, dict(task["canonical_inputs"]))
    projected = {
        output_key: nested(execution, source_path)
        for output_key, source_path in projection.items()
    }
    scoring = score_projected_output(task, projected)
    acceptable = execution.get("success") is True and scoring["passed"]
    return {
        "candidate_tool_id": tool_id,
        "input": task["canonical_inputs"],
        "execution": execution,
        "projected_task_output": projected,
        "scoring": scoring,
        "directly_acceptable": acceptable,
    }


def build(
    config: dict[str, Any],
    *,
    invoke_fn: Callable[[str, dict[str, Any]], dict[str, Any]] = invoke,
    validate_runtime_environment: bool = True,
) -> dict[str, Any]:
    for field in (
        "full_137_registry_gold_claim_allowed",
        "confirmatory_use_allowed",
        "external_api_calls_authorized",
        "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")
    paths = {
        name: validate_binding(binding)
        for name, binding in config["bindings"].items()
    }
    sources = {
        name: load_json(path)
        for name, path in paths.items()
        if path.suffix.lower() == ".json"
    }
    environment = (
        validate_environment(sources)
        if validate_runtime_environment
        else {"environment_match": "test_injection"}
    )
    registry = {
        row["candidate_tool_id"]: row
        for row in sources["candidate_registry_batch1"]["candidates"]
    }
    tasks = sources["development_taskset"]["tasks"]
    neighbor_matrix = sources["base_neighbor_matrix"]
    relation_registry = sources["combined_relation_registry"]

    task_rows = []
    execution_rows = []
    screening_rows = []
    target_summaries = []
    for target_id in config["target_tool_ids"]:
        policy = config["target_policies"][target_id]
        direct_ids = set(policy["direct_candidate_tool_ids"])
        excluded_ids = set(policy["excluded_neighbor_tool_ids"])
        scoped_neighbor_ids = candidate_scope_ids(
            target_id, neighbor_matrix, relation_registry
        )
        if scoped_neighbor_ids != excluded_ids | (direct_ids & scoped_neighbor_ids):
            raise ValueError(
                f"candidate scope classification is incomplete for {target_id}: "
                f"observed={sorted(scoped_neighbor_ids)}"
            )
        for tool_id in direct_ids:
            if tool_id not in registry:
                raise ValueError(f"direct candidate is not in batch-1 registry: {tool_id}")
        screening_rows.append(
            {
                "target_tool_id": target_id,
                "scoped_neighbor_tool_ids": sorted(scoped_neighbor_ids),
                "direct_candidate_tool_ids": sorted(direct_ids),
                "excluded_neighbor_tool_ids": sorted(excluded_ids),
                "excluded_neighbor_reason": config["excluded_neighbor_reason"],
                "classification_complete": True,
            }
        )

        target_tasks = [row for row in tasks if row["source_tool_id"] == target_id]
        target_acceptances = {tool_id: 0 for tool_id in direct_ids}
        for task in target_tasks:
            accepted = [target_id]
            evaluations = []
            for tool_id in sorted(direct_ids):
                evaluation = evaluate_candidate(
                    task,
                    tool_id,
                    policy["direct_result_projection"][tool_id],
                    invoke_fn,
                )
                evaluations.append(evaluation)
                execution_rows.append(
                    {"task_id": task["task_id"], "target_tool_id": target_id, **evaluation}
                )
                if evaluation["directly_acceptable"]:
                    accepted.append(tool_id)
                    target_acceptances[tool_id] += 1
            task_rows.append(
                {
                    "task_id": task["task_id"],
                    "target_tool_id": target_id,
                    "problem_text": task["problem_text"],
                    "canonical_inputs": task["canonical_inputs"],
                    "scoring_rule": task["scoring_rule"],
                    "original_acceptable_tools": task["acceptable_tools"],
                    "revalidated_primary_acceptable_tools": accepted,
                    "direct_candidate_evaluations": evaluations,
                    "candidate_scope": config["candidate_scope"],
                    "full_137_registry_gold_claim_allowed": False,
                }
            )
        target_summaries.append(
            {
                "target_tool_id": target_id,
                "task_count": len(target_tasks),
                "direct_candidate_acceptance_counts": target_acceptances,
                "singleton_acceptable_set_count": sum(
                    len(row["revalidated_primary_acceptable_tools"]) == 1
                    for row in task_rows
                    if row["target_tool_id"] == target_id
                ),
                "multiple_acceptable_set_count": sum(
                    len(row["revalidated_primary_acceptable_tools"]) > 1
                    for row in task_rows
                    if row["target_tool_id"] == target_id
                ),
            }
        )

    observed_failure_task_ids = sorted(
        {
            row["task_id"]
            for row in execution_rows
            if row["execution"].get("success") is not True
        }
    )
    expected_failure_task_ids = sorted(
        {
            task_id
            for policy in config["target_policies"].values()
            for task_id in policy["expected_contract_inapplicable_task_ids"]
        }
    )
    unexpected_failure_task_ids = sorted(
        set(observed_failure_task_ids) - set(expected_failure_task_ids)
    )
    missing_expected_failure_task_ids = sorted(
        set(expected_failure_task_ids) - set(observed_failure_task_ids)
    )
    execution_outcomes_match_policy = (
        not unexpected_failure_task_ids and not missing_expected_failure_task_ids
    )
    report = {
        "schema_version": "1.0",
        "revalidation_id": config["revalidation_id"],
        "status": "non_a003_task_gold_candidate_revalidated_for_development_scope",
        "selection_estimand": config["selection_estimand"],
        "candidate_scope": config["candidate_scope"],
        "target_count": len(config["target_tool_ids"]),
        "task_count": len(task_rows),
        "execution_count": len(execution_rows),
        "all_direct_candidate_executions_succeeded": all(
            row["execution"].get("success") is True for row in execution_rows
        ),
        "observed_contract_inapplicable_task_ids": observed_failure_task_ids,
        "expected_contract_inapplicable_task_ids": expected_failure_task_ids,
        "unexpected_execution_failure_task_ids": unexpected_failure_task_ids,
        "missing_expected_failure_task_ids": missing_expected_failure_task_ids,
        "all_execution_outcomes_match_policy": execution_outcomes_match_policy,
        "target_summaries": target_summaries,
        "full_137_registry_gold_claim_allowed": False,
        "development_mixed_realistic_opening_allowed": (
            config["development_mixed_realistic_opening_allowed_after_pass"]
            and execution_outcomes_match_policy
        ),
        "environment": environment,
        "external_api_calls": 0,
        "tool_executions": len(execution_rows),
        "confirmatory_use_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "next_gate": "build the no-API 17/120 mixed-realistic multi-target development opening package",
    }
    return {
        "report": report,
        "task_rows": task_rows,
        "execution_rows": execution_rows,
        "screening_rows": screening_rows,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    result = build(config)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "multitarget_task_gold_config_snapshot.json": config,
        "multitarget_task_gold_report.json": result["report"],
        "multitarget_task_acceptable_tools_registry.json": {"tasks": result["task_rows"]},
        "direct_candidate_execution_results.json": {"rows": result["execution_rows"]},
        "candidate_scope_screening.json": {"rows": result["screening_rows"]},
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = build_outputs(args.output_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
