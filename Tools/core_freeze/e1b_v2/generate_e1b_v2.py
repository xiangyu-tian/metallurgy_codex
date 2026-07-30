"""Generate the leakage-controlled E1b v2 task set.

Reference answers in this module are computed from frozen seed facts and
elementary equations.  This module deliberately does not import the production
tool registry or any production tool implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
CORE_FREEZE_DIR = HERE.parent
PROJECT_ROOT = HERE.parents[2]
VERIFIED_DIR = CORE_FREEZE_DIR / "verified_core"

CONDITIONS = [
    {
        "condition": "no_tool",
        "tool_access": "disabled",
        "oracle_parameters": None,
    },
    {
        "condition": "forced_verified_oracle_parameters",
        "tool_access": "forced",
    },
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_relative(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT).as_posix()


def stable_seed(task_id: str) -> int:
    return int(hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:8], 16)


def display_number(value: float) -> str:
    return format(value, ".12g")


def answer_schema(properties: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": list(properties),
        "properties": {
            name: {"type": value_type}
            for name, value_type in properties.items()
        },
    }


def contract_map(contracts_doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["tool_id"]: row
        for row in contracts_doc["contracts"]
        if row["tool_status"] == "verified_core"
    }


def make_task(
    *,
    task_id: str,
    group_id: str,
    split: str,
    precision_policy: str,
    tool_id: str,
    contract: dict[str, Any],
    generator_version: str,
    problem_text: str,
    inputs: dict[str, Any],
    schema: dict[str, Any],
    checks: list[dict[str, Any]],
    oracle_basis: str,
) -> dict[str, Any]:
    conditions = [dict(row) for row in CONDITIONS]
    conditions[1]["forced_tool_id"] = tool_id
    conditions[1]["oracle_parameters"] = inputs
    return {
        "task_id": task_id,
        "task_family_id": f"E1B-{tool_id}",
        "task_pair_id": f"PAIR-{task_id}",
        "base_task_group_id": group_id,
        "split": split,
        "precision_policy": precision_policy,
        "data_layer": "controlled_executable_truth",
        "source_type": "independent_contract_generator",
        "source_tool_id": tool_id,
        "source_tool_version": contract["tool_version"],
        "contract_id": contract["contract_id"],
        "contract_hash": contract["contract_hash"],
        "generator_version": generator_version,
        "random_seed": stable_seed(task_id),
        "problem_text": problem_text,
        "canonical_inputs": inputs,
        "expected_parameters": inputs,
        "acceptable_tools": [tool_id],
        "answer_schema": schema,
        "scoring_rule": {
            "rule_id": f"E1B-{tool_id}-PRIMARY-v2",
            "type": "structured_path_checks",
            "checks": checks,
        },
        "reference_execution": {
            "oracle_version": "independent-equations-v2",
            "oracle_basis": oracle_basis,
            "expected_checks": checks,
            "production_code_imported": False,
        },
        "conditions": conditions,
        "confirmatory_eligibility": "development_candidate",
    }


def build_a001(
    seeds: dict[str, Any],
    contracts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    tasks = []
    counter = 0
    for group in seeds["a001_groups"]:
        for value in group["values"]:
            counter += 1
            task_id = f"E1B2-A001-{counter:03d}"
            expected = round(
                value * group["factor"] + group["offset"],
                10,
            )
            tolerance = max(1e-9, abs(expected) * 1e-12)
            inputs = {
                "value": value,
                "source_unit": group["source_unit"],
                "target_unit": group["target_unit"],
            }
            tasks.append(
                make_task(
                    task_id=task_id,
                    group_id=group["group_id"],
                    split=group["split"],
                    precision_policy="contract_numeric",
                    tool_id="A001",
                    contract=contracts["A001"],
                    generator_version=seeds["generator_version"],
                    problem_text=(
                        f"请将 {display_number(value)} {group['source_unit']} "
                        f"换算为 {group['target_unit']}。只返回换算后的数值。"
                    ),
                    inputs=inputs,
                    schema=answer_schema({"value": "number"}),
                    checks=[
                        {
                            "path": "value",
                            "op": "approx",
                            "value": expected,
                            "abs_tol": tolerance,
                            "rel_tol": 0.0,
                        }
                    ],
                    oracle_basis=(
                        "Independent affine conversion: "
                        "target = source * frozen factor + frozen offset"
                    ),
                )
            )
    return tasks


def build_a002(
    seeds: dict[str, Any],
    contracts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    tasks = []
    for counter, group in enumerate(seeds["a002_groups"], start=1):
        task_id = f"E1B2-A002-{counter:03d}"
        inputs = {"formula": group["formula"]}
        tasks.append(
            make_task(
                task_id=task_id,
                group_id=group["group_id"],
                split=group["split"],
                precision_policy="exact_stoichiometric_counts",
                tool_id="A002",
                contract=contracts["A002"],
                generator_version=seeds["generator_version"],
                problem_text=(
                    f"解析中性化学式 {group['formula']}，返回各元素的化学计量数。"
                ),
                inputs=inputs,
                schema=answer_schema({"elements": "object"}),
                checks=[
                    {
                        "path": "elements",
                        "op": "equal",
                        "value": group["elements"],
                    }
                ],
                oracle_basis="Explicit human-readable stoichiometric counts in frozen seeds",
            )
        )
    return tasks


def build_a003(
    seeds: dict[str, Any],
    contracts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    tasks = []
    counter = 0
    weights = seeds["atomic_weights"]
    for group in seeds["a003_groups"]:
        unsupported = sorted(set(group["elements"]) - set(weights))
        if unsupported:
            raise ValueError(
                f"{group['group_id']} uses unfrozen elements: {unsupported}"
            )
        expected = round(
            sum(
                float(count) * float(weights[element])
                for element, count in group["elements"].items()
            ),
            4,
        )
        used_weights = "，".join(
            f"{element}={display_number(weights[element])}"
            for element in group["elements"]
        )
        for policy, tolerance, instruction in (
            (
                "strict_versioned",
                0.0001,
                "按上述原子量计算并保留4位小数",
            ),
            (
                "approximate_educational",
                0.1,
                "给出近似结果，允许绝对误差不超过0.1 g/mol",
            ),
        ):
            counter += 1
            task_id = f"E1B2-A003-{counter:03d}"
            inputs = {"formula": group["formula"]}
            tasks.append(
                make_task(
                    task_id=task_id,
                    group_id=group["group_id"],
                    split=group["split"],
                    precision_policy=policy,
                    tool_id="A003",
                    contract=contracts["A003"],
                    generator_version=seeds["generator_version"],
                    problem_text=(
                        f"使用冻结原子量（{used_weights}）计算 "
                        f"{group['formula']} 的摩尔质量。{instruction}。"
                    ),
                    inputs=inputs,
                    schema=answer_schema({"molar_mass": "number"}),
                    checks=[
                        {
                            "path": "molar_mass",
                            "op": "approx",
                            "value": expected,
                            "abs_tol": tolerance,
                            "rel_tol": 0.0,
                        }
                    ],
                    oracle_basis=(
                        "Independent sum of explicit stoichiometric counts "
                        "times frozen atomic weights"
                    ),
                )
            )
    return tasks


def build_a004(
    seeds: dict[str, Any],
    contracts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    tasks = []
    counter = 0
    for group in seeds["a004_groups"]:
        for compositions in group["variants"]:
            counter += 1
            task_id = f"E1B2-A004-{counter:03d}"
            total = sum(float(value) for value in compositions.values())
            normalized = {
                name: round(float(value) / total, 6)
                for name, value in compositions.items()
            }
            inputs = {"compositions": compositions}
            tasks.append(
                make_task(
                    task_id=task_id,
                    group_id=group["group_id"],
                    split=group["split"],
                    precision_policy="six_decimal_components",
                    tool_id="A004",
                    contract=contracts["A004"],
                    generator_version=seeds["generator_version"],
                    problem_text=(
                        "以下组分使用同一基准："
                        f"{json.dumps(compositions, ensure_ascii=False, sort_keys=True)}。"
                        "请归一化各组分，使总和为1；各分量保留6位小数。"
                    ),
                    inputs=inputs,
                    schema=answer_schema({"normalized": "object"}),
                    checks=[
                        {
                            "path": "normalized",
                            "op": "equal",
                            "value": normalized,
                        }
                    ],
                    oracle_basis="Independent component divided by positive finite sum",
                )
            )
    return tasks


def build_b019(
    seeds: dict[str, Any],
    contracts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    tasks = []
    counter = 0
    for group in seeds["b019_groups"]:
        denominator = group["phase2"] - group["phase1"]
        phase1_fraction = round(
            (group["phase2"] - group["overall"]) / denominator,
            6,
        )
        phase2_fraction = round(
            (group["overall"] - group["phase1"]) / denominator,
            6,
        )
        for basis, scale in (("fraction", 1.0), ("percent", 100.0)):
            counter += 1
            task_id = f"E1B2-B019-{counter:03d}"
            inputs = {
                "overall_composition": group["overall"] * scale,
                "phase1_composition": group["phase1"] * scale,
                "phase2_composition": group["phase2"] * scale,
                "composition_basis": basis,
            }
            tasks.append(
                make_task(
                    task_id=task_id,
                    group_id=group["group_id"],
                    split=group["split"],
                    precision_policy=f"{basis}_explicit_six_decimal",
                    tool_id="B019",
                    contract=contracts["B019"],
                    generator_version=seeds["generator_version"],
                    problem_text=(
                        "在二元两相区同一条已知等温连线上，"
                        f"总体成分为 {display_number(inputs['overall_composition'])}，"
                        f"相1边界成分为 {display_number(inputs['phase1_composition'])}，"
                        f"相2边界成分为 {display_number(inputs['phase2_composition'])}，"
                        f"三者均使用 {basis} 标度。计算相1和相2的相分数，"
                        "结果保留6位小数。"
                    ),
                    inputs=inputs,
                    schema=answer_schema(
                        {
                            "phase1_fraction": "number",
                            "phase2_fraction": "number",
                        }
                    ),
                    checks=[
                        {
                            "path": "phase1_fraction",
                            "op": "approx",
                            "value": phase1_fraction,
                            "abs_tol": 1e-6,
                            "rel_tol": 0.0,
                        },
                        {
                            "path": "phase2_fraction",
                            "op": "approx",
                            "value": phase2_fraction,
                            "abs_tol": 1e-6,
                            "rel_tol": 0.0,
                        },
                    ],
                    oracle_basis=(
                        "Independent solution of f1+f2=1 and "
                        "C0=f1*C1+f2*C2"
                    ),
                )
            )
    return tasks


def build_tasks(
    seeds_doc: dict[str, Any],
    contracts_doc: dict[str, Any],
) -> list[dict[str, Any]]:
    contracts = contract_map(contracts_doc)
    required = {"A001", "A002", "A003", "A004", "B019"}
    if not required.issubset(contracts):
        raise ValueError(
            f"missing verified contracts: {sorted(required - set(contracts))}"
        )
    tasks = []
    tasks.extend(build_a001(seeds_doc, contracts))
    tasks.extend(build_a002(seeds_doc, contracts))
    tasks.extend(build_a003(seeds_doc, contracts))
    tasks.extend(build_a004(seeds_doc, contracts))
    tasks.extend(build_b019(seeds_doc, contracts))
    return tasks


def structural_errors(
    tasks: list[dict[str, Any]],
    contracts_doc: dict[str, Any],
) -> list[str]:
    errors = []
    contracts = contract_map(contracts_doc)
    expected_tool_counts = {
        "A001": 16,
        "A002": 12,
        "A003": 20,
        "A004": 12,
        "B019": 12,
    }
    expected_split_counts = {
        "benefit_estimation": 45,
        "gate_evaluation": 27,
    }
    ids = [task["task_id"] for task in tasks]
    pair_ids = [task["task_pair_id"] for task in tasks]
    if len(ids) != len(set(ids)):
        errors.append("duplicate task_id")
    if len(pair_ids) != len(set(pair_ids)):
        errors.append("duplicate task_pair_id")
    if Counter(task["source_tool_id"] for task in tasks) != Counter(
        expected_tool_counts
    ):
        errors.append("unexpected task counts by tool")
    if Counter(task["split"] for task in tasks) != Counter(expected_split_counts):
        errors.append("unexpected task counts by split")

    group_splits: dict[str, set[str]] = {}
    for task in tasks:
        group_splits.setdefault(task["base_task_group_id"], set()).add(task["split"])
        contract = contracts.get(task["source_tool_id"])
        if contract is None:
            errors.append(f"{task['task_id']}: source tool is not verified_core")
            continue
        if task["contract_id"] != contract["contract_id"]:
            errors.append(f"{task['task_id']}: contract id mismatch")
        if task["contract_hash"] != contract["contract_hash"]:
            errors.append(f"{task['task_id']}: contract hash mismatch")
        if task["acceptable_tools"] != [task["source_tool_id"]]:
            errors.append(f"{task['task_id']}: acceptable_tools is not singleton")
        if task["canonical_inputs"] != task["expected_parameters"]:
            errors.append(f"{task['task_id']}: expected parameters differ")
        condition_names = [row["condition"] for row in task["conditions"]]
        if condition_names != [
            "no_tool",
            "forced_verified_oracle_parameters",
        ]:
            errors.append(f"{task['task_id']}: invalid condition pair")
        if task["reference_execution"]["production_code_imported"] is not False:
            errors.append(f"{task['task_id']}: reference is not independent")
    leaking = sorted(group for group, splits in group_splits.items() if len(splits) > 1)
    if leaking:
        errors.append(f"base-task groups cross splits: {leaking}")

    a003_groups: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        if task["source_tool_id"] == "A003":
            a003_groups.setdefault(task["base_task_group_id"], []).append(task)
    for group, rows in a003_groups.items():
        policies = {row["precision_policy"] for row in rows}
        if policies != {"strict_versioned", "approximate_educational"}:
            errors.append(f"{group}: incomplete A003 precision pair")
        if len({row["split"] for row in rows}) != 1:
            errors.append(f"{group}: A003 precision pair crosses splits")
    return errors


def generate(
    seeds_path: Path,
    contracts_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    seeds_doc = load_json(seeds_path)
    contracts_doc = load_json(contracts_path)
    tasks = build_tasks(seeds_doc, contracts_doc)
    errors = structural_errors(tasks, contracts_doc)
    if errors:
        raise ValueError("; ".join(errors))

    output_dir.mkdir(parents=True, exist_ok=True)
    tasks_path = output_dir / "e1b_tasks_v2.json"
    tasks_doc = {
        "schema_version": "2.0",
        "dataset_id": "E1B-TASKSET-V2-20260730",
        "dataset_status": "prepared",
        "protocol_version": "research_protocol_v1.1-rc1",
        "generator_version": seeds_doc["generator_version"],
        "generated_at": seeds_doc["generated_at"],
        "split_policy": seeds_doc["split_policy"],
        "primary_contrast": [
            "forced_verified_oracle_parameters",
            "no_tool",
        ],
        "task_count": len(tasks),
        "tasks": tasks,
        "core_frozen": False,
    }
    write_json(tasks_path, tasks_doc)

    report_path = output_dir / "generation_report.json"
    report = {
        "schema_version": "2.0",
        "dataset_id": tasks_doc["dataset_id"],
        "status": "passed",
        "task_count": len(tasks),
        "condition_run_cells_before_repeats": len(tasks) * 2,
        "task_count_by_tool": dict(
            sorted(Counter(task["source_tool_id"] for task in tasks).items())
        ),
        "task_count_by_split": dict(
            sorted(Counter(task["split"] for task in tasks).items())
        ),
        "a003_count_by_precision_policy": dict(
            sorted(
                Counter(
                    task["precision_policy"]
                    for task in tasks
                    if task["source_tool_id"] == "A003"
                ).items()
            )
        ),
        "reference_generation": {
            "production_tool_code_imported": False,
            "basis": "frozen facts plus independent elementary equations",
        },
        "structural_validation_errors": [],
        "production_validation_status": "pending",
        "limitations": [
            "prepared means task construction passed; it does not mean model API runs were performed",
            "gate_evaluation is held out from benefit-estimation decisions",
            "development_candidate is not equivalent to confirmatory gold",
        ],
        "core_frozen": False,
    }
    write_json(report_path, report)

    manifest_path = output_dir / "artifact_manifest.json"
    manifest = {
        "schema_version": "2.0",
        "dataset_id": tasks_doc["dataset_id"],
        "validation_status": "pending",
        "artifacts": [
            {"filename": tasks_path.name, "sha256": file_hash(tasks_path)},
            {"filename": report_path.name, "sha256": file_hash(report_path)},
            {
                "filename": project_relative(seeds_path),
                "sha256": file_hash(seeds_path),
            },
            {
                "filename": project_relative(contracts_path),
                "sha256": file_hash(contracts_path),
            },
        ],
    }
    write_json(manifest_path, manifest)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seeds",
        type=Path,
        default=HERE / "task_seeds_v2.json",
    )
    parser.add_argument(
        "--contracts",
        type=Path,
        default=VERIFIED_DIR / "contracts_v1.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "e1b_taskset_v2_20260730",
    )
    args = parser.parse_args()
    report = generate(args.seeds, args.contracts, args.output_dir)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
