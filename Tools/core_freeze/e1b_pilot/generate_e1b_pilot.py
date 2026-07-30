"""Generate E1b No-Tool versus Forced-Verified-Tool pilot task pairs."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
CORE_FREEZE_DIR = HERE.parent
VERIFIED_DIR = CORE_FREEZE_DIR / "verified_core"
PROJECT_ROOT = HERE.parents[2]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_relative(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT).as_posix()


def stable_seed(case_id: str) -> int:
    return int(hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:8], 16)


def format_problem(template: str, params: dict[str, Any]) -> str:
    values = dict(params)
    if "compositions" in values:
        values["compositions_json"] = json.dumps(
            values["compositions"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return template.format(**values)


def build_score_targets(
    expected: dict[str, Any],
    primary_paths: list[str],
) -> list[dict[str, Any]]:
    checks_by_path = {
        check["path"]: check for check in expected.get("checks", [])
    }
    missing = [path for path in primary_paths if path not in checks_by_path]
    if missing:
        raise ValueError(f"reference case lacks primary checks: {missing}")
    return [checks_by_path[path] for path in primary_paths]


def build_tasks(
    contracts_doc: dict[str, Any],
    cases_doc: dict[str, Any],
    templates_doc: dict[str, Any],
) -> list[dict[str, Any]]:
    contracts = {
        row["tool_id"]: row
        for row in contracts_doc["contracts"]
        if row["tool_status"] == "verified_core"
    }
    templates = templates_doc["templates"]
    tasks = []

    eligible_cases = [
        case
        for case in cases_doc["cases"]
        if case["expected"]["success"]
        and case["tool_id"] in contracts
        and case["tool_id"] in templates
    ]
    for index, case in enumerate(eligible_cases, start=1):
        tool_id = case["tool_id"]
        contract = contracts[tool_id]
        template = templates[tool_id]
        task_id = f"E1B-{tool_id}-{index:03d}"
        score_targets = build_score_targets(
            case["expected"],
            template["primary_result_paths"],
        )
        tasks.append(
            {
                "task_id": task_id,
                "task_family_id": f"E1B-{tool_id}",
                "task_pair_id": f"PAIR-{task_id}",
                "data_layer": "controlled_confirmatory_pilot",
                "source_type": "contract_generated",
                "source_reference_case_id": case["case_id"],
                "source_tool_id": tool_id,
                "source_tool_version": contract["tool_version"],
                "contract_id": contract["contract_id"],
                "contract_hash": contract["contract_hash"],
                "generator_version": templates_doc["generator_version"],
                "random_seed": stable_seed(case["case_id"]),
                "problem_text": format_problem(
                    template["problem_template"],
                    case["input"],
                ),
                "canonical_inputs": case["input"],
                "expected_parameters": case["input"],
                "acceptable_tools": [tool_id],
                "answer_schema": template["answer_schema"],
                "scoring_rule": {
                    "rule_id": f"E1B-{tool_id}-PRIMARY-v1",
                    "type": "structured_path_checks",
                    "checks": score_targets,
                },
                "reference_execution": {
                    "reference_case_id": case["case_id"],
                    "oracle_version": cases_doc["oracle_version"],
                    "oracle_basis": case["oracle_basis"],
                    "expected_checks": score_targets,
                },
                "conditions": [
                    {
                        "condition": "no_tool",
                        "tool_access": "disabled",
                        "oracle_parameters": None,
                    },
                    {
                        "condition": "forced_verified_oracle_parameters",
                        "tool_access": "forced",
                        "forced_tool_id": tool_id,
                        "oracle_parameters": case["input"],
                    },
                ],
                "confirmatory_eligibility": "pilot_candidate",
            }
        )
    return tasks


def validate_tasks(
    tasks: list[dict[str, Any]],
    contracts_doc: dict[str, Any],
) -> list[str]:
    errors = []
    verified_contracts = {
        row["tool_id"]: row
        for row in contracts_doc["contracts"]
        if row["tool_status"] == "verified_core"
    }
    task_ids = [task["task_id"] for task in tasks]
    pair_ids = [task["task_pair_id"] for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        errors.append("duplicate task_id")
    if len(pair_ids) != len(set(pair_ids)):
        errors.append("duplicate task_pair_id")

    for task in tasks:
        tool_id = task["source_tool_id"]
        contract = verified_contracts.get(tool_id)
        if contract is None:
            errors.append(f"{task['task_id']}: source tool is not verified_core")
            continue
        if task["contract_hash"] != contract["contract_hash"]:
            errors.append(f"{task['task_id']}: contract hash mismatch")
        if task["acceptable_tools"] != [tool_id]:
            errors.append(f"{task['task_id']}: acceptable_tools is not singleton source")
        conditions = [row["condition"] for row in task["conditions"]]
        if conditions != ["no_tool", "forced_verified_oracle_parameters"]:
            errors.append(f"{task['task_id']}: invalid primary condition pair")
        if not task["scoring_rule"]["checks"]:
            errors.append(f"{task['task_id']}: empty scoring checks")
        if tool_id == "B019":
            basis = task["canonical_inputs"].get("composition_basis")
            if basis not in {"fraction", "percent"}:
                errors.append(
                    f"{task['task_id']}: B019 requires explicit composition_basis"
                )
    return errors


def generate(
    contracts_path: Path,
    cases_path: Path,
    templates_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    contracts_doc = load_json(contracts_path)
    cases_doc = load_json(cases_path)
    templates_doc = load_json(templates_path)
    tasks = build_tasks(contracts_doc, cases_doc, templates_doc)
    errors = validate_tasks(tasks, contracts_doc)
    if errors:
        raise ValueError("; ".join(errors))

    output_dir.mkdir(parents=True, exist_ok=True)
    tasks_path = output_dir / "e1b_tasks.json"
    tasks_doc = {
        "schema_version": "1.0",
        "dataset_id": "E1B-PILOT-V1-20260730",
        "dataset_status": "prepared",
        "protocol_version": "research_protocol_v1.1-rc1",
        "generator_version": templates_doc["generator_version"],
        "generated_at": templates_doc["generated_at"],
        "primary_contrast": [
            "forced_verified_oracle_parameters",
            "no_tool",
        ],
        "task_count": len(tasks),
        "tasks": tasks,
        "core_frozen": False,
    }
    tasks_path.write_text(
        json.dumps(tasks_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report_path = output_dir / "generation_report.json"
    report = {
        "schema_version": "1.0",
        "dataset_id": tasks_doc["dataset_id"],
        "status": "passed",
        "task_count": len(tasks),
        "condition_run_cells_before_repeats": len(tasks) * 2,
        "task_count_by_tool": dict(
            sorted(Counter(task["source_tool_id"] for task in tasks).items())
        ),
        "validation_errors": [],
        "limitations": [
            "prepared表示任务与评分接口通过，不表示模型实验已经运行",
            "任务仅覆盖verified_core v1合同范围",
            "正式重复次数、模型清单和功效分析尚未冻结",
        ],
        "core_frozen": False,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest_path = output_dir / "artifact_manifest.json"
    manifest = {
        "schema_version": "1.0",
        "dataset_id": tasks_doc["dataset_id"],
        "artifacts": [
            {"filename": tasks_path.name, "sha256": file_hash(tasks_path)},
            {"filename": report_path.name, "sha256": file_hash(report_path)},
            {
                "filename": project_relative(contracts_path),
                "sha256": file_hash(contracts_path),
            },
            {
                "filename": project_relative(cases_path),
                "sha256": file_hash(cases_path),
            },
            {
                "filename": project_relative(templates_path),
                "sha256": file_hash(templates_path),
            },
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contracts",
        type=Path,
        default=VERIFIED_DIR / "contracts_v1.json",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=VERIFIED_DIR / "reference_cases_v1.json",
    )
    parser.add_argument(
        "--templates",
        type=Path,
        default=HERE / "templates_v1.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "e1b_pilot_v1_20260730",
    )
    args = parser.parse_args()
    report = generate(
        args.contracts,
        args.cases,
        args.templates,
        args.output_dir,
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
