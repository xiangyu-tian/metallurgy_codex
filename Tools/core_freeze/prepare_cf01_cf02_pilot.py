"""Build the frozen CF-01/CF-02 pilot preparation package.

The generated files deliberately separate annotator-facing tasks from
administrator-only coverage targets and legacy routing hints.  Legacy labels
are migration references, not Dataset 2.0 gold labels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "pilot_v1"
LEGACY_DATASET = PROJECT_ROOT / "Tools" / "benchmarks" / "tool_calling_cases.json"
GENERATED_AT = "2026-07-28T00:00:00+08:00"


TRACK_A_SPECS: list[dict[str, Any]] = [
    {
        "task_id": "TA-PILOT-001",
        "question": "什么是摩尔质量？",
        "context": None,
        "source": {"type": "authored_minimal_pair", "legacy_case_id": None},
        "minimal_difference_group": "molar_mass_evidence",
        "anticipated_coverage": {
            "evidence_requirement": ["none"],
            "answerability": ["answerable"],
            "information_status": ["sufficient"],
            "capability_status": ["available"],
            "risk_status": ["normal"],
        },
    },
    {
        "task_id": "TA-PILOT-002",
        "question": "Fe₂O₃ 的摩尔质量是多少？请写出计算过程。",
        "context": None,
        "source": {
            "type": "adapted_legacy",
            "legacy_case_id": "TC-SINGLE_TOOL-007",
        },
        "minimal_difference_group": "molar_mass_evidence",
        "anticipated_coverage": {
            "evidence_requirement": ["optional"],
            "answerability": ["answerable"],
            "information_status": ["sufficient"],
            "capability_status": ["available"],
            "risk_status": ["normal"],
        },
    },
    {
        "task_id": "TA-PILOT-003",
        "question": "按 IUPAC 2021 原子量计算 Fe₂O₃ 的摩尔质量，给出数据版本、计算记录和可追溯结果。",
        "context": None,
        "source": {"type": "authored_minimal_pair", "legacy_case_id": None},
        "minimal_difference_group": "molar_mass_evidence",
        "anticipated_coverage": {
            "evidence_requirement": ["required"],
            "answerability": ["answerable"],
            "information_status": ["sufficient"],
            "capability_status": ["available"],
            "risk_status": ["normal"],
        },
    },
    {
        "task_id": "TA-PILOT-004",
        "question": "按企业指定原子量数据版本计算 Fe₂O₃ 的摩尔质量，用于自动投料设定；请直接给出可执行值。",
        "context": "企业指定的数据版本未提供。",
        "source": {"type": "authored_boundary_case", "legacy_case_id": None},
        "minimal_difference_group": "molar_mass_evidence",
        "anticipated_coverage": {
            "evidence_requirement": ["required"],
            "answerability": ["answerable"],
            "information_status": ["missing_execution_input"],
            "capability_status": ["available"],
            "risk_status": ["review_required"],
        },
    },
    {
        "task_id": "TA-PILOT-005",
        "question": "解释 Gibbs 自由能如何判断反应方向。",
        "context": None,
        "source": {
            "type": "adapted_legacy",
            "legacy_case_id": "TC-NO_TOOL-008",
        },
        "minimal_difference_group": "gibbs_readiness",
        "anticipated_coverage": {
            "evidence_requirement": ["none"],
            "answerability": ["answerable"],
            "information_status": ["sufficient"],
            "capability_status": ["available"],
            "risk_status": ["normal"],
        },
    },
    {
        "task_id": "TA-PILOT-006",
        "question": "计算反应 C + O₂ → CO₂ 在 1000 K 的反应 Gibbs 自由能并判断方向。",
        "context": None,
        "source": {
            "type": "adapted_legacy",
            "legacy_case_id": "TC-SINGLE_TOOL-038",
        },
        "minimal_difference_group": "gibbs_readiness",
        "anticipated_coverage": {
            "evidence_requirement": ["required"],
            "answerability": ["answerable"],
            "information_status": ["sufficient"],
            "capability_status": ["available"],
            "risk_status": ["normal"],
        },
    },
    {
        "task_id": "TA-PILOT-007",
        "question": "请计算反应 Gibbs 自由能。",
        "context": None,
        "source": {
            "type": "adapted_legacy",
            "legacy_case_id": "TC-INSUFFICIENT_INFO-003",
        },
        "minimal_difference_group": "gibbs_readiness",
        "anticipated_coverage": {
            "evidence_requirement": ["required"],
            "answerability": ["missing_task_information"],
            "information_status": ["missing_execution_input"],
            "capability_status": ["available"],
            "risk_status": ["normal"],
        },
    },
    {
        "task_id": "TA-PILOT-008",
        "question": "计算这个反应在 1000 K 的 Gibbs 自由能。",
        "context": "当前对话没有给出“这个反应”所指的反应式。",
        "source": {"type": "authored_minimal_pair", "legacy_case_id": None},
        "minimal_difference_group": "gibbs_readiness",
        "anticipated_coverage": {
            "evidence_requirement": ["required"],
            "answerability": ["missing_task_information"],
            "information_status": ["missing_execution_input"],
            "capability_status": ["available"],
            "risk_status": ["normal"],
        },
    },
    {
        "task_id": "TA-PILOT-009",
        "question": "什么是定压热容？",
        "context": None,
        "source": {
            "type": "adapted_legacy",
            "legacy_case_id": "TC-NO_TOOL-009",
        },
        "minimal_difference_group": "heat_capacity_readiness",
        "anticipated_coverage": {
            "evidence_requirement": ["none"],
            "answerability": ["answerable"],
            "information_status": ["sufficient"],
            "capability_status": ["available"],
            "risk_status": ["normal"],
        },
    },
    {
        "task_id": "TA-PILOT-010",
        "question": "使用 Shomate 方程计算 1000 K 时 Fe(s) 的定压热容 Cp。",
        "context": None,
        "source": {
            "type": "legacy_exact",
            "legacy_case_id": "TC-SINGLE_TOOL-018",
        },
        "minimal_difference_group": "heat_capacity_readiness",
        "anticipated_coverage": {
            "evidence_requirement": ["required"],
            "answerability": ["answerable"],
            "information_status": ["sufficient"],
            "capability_status": ["available"],
            "risk_status": ["normal"],
        },
    },
    {
        "task_id": "TA-PILOT-011",
        "question": "计算这个物种的定压热容。",
        "context": None,
        "source": {
            "type": "legacy_exact",
            "legacy_case_id": "TC-INSUFFICIENT_INFO-002",
        },
        "minimal_difference_group": "heat_capacity_readiness",
        "anticipated_coverage": {
            "evidence_requirement": ["required"],
            "answerability": ["missing_task_information"],
            "information_status": ["missing_execution_input"],
            "capability_status": ["available"],
            "risk_status": ["normal"],
        },
    },
    {
        "task_id": "TA-PILOT-012",
        "question": "计算温度为 1000 时 Fe 的定压热容。",
        "context": "温度数值没有注明单位，Fe 的相态也没有说明。",
        "source": {"type": "authored_boundary_case", "legacy_case_id": None},
        "minimal_difference_group": "heat_capacity_readiness",
        "anticipated_coverage": {
            "evidence_requirement": ["required"],
            "answerability": ["answerable"],
            "information_status": ["ambiguous_execution_input"],
            "capability_status": ["available"],
            "risk_status": ["normal"],
        },
    },
    {
        "task_id": "TA-PILOT-013",
        "question": "用当前平台计算铝电解槽三维磁流体耦合场，并给出槽内波动随时间的结果。",
        "context": None,
        "source": {"type": "authored_capability_boundary", "legacy_case_id": None},
        "minimal_difference_group": "capability_boundary",
        "anticipated_coverage": {
            "evidence_requirement": ["required"],
            "answerability": ["answerable"],
            "information_status": ["missing_execution_input"],
            "capability_status": ["unavailable"],
            "risk_status": ["normal"],
        },
    },
    {
        "task_id": "TA-PILOT-014",
        "question": "平台能否计算给定成分和温度下 CaO-SiO₂-Al₂O₃ 炉渣的黏度？",
        "context": "用户只询问能力，没有提交具体成分和温度。",
        "source": {"type": "authored_capability_boundary", "legacy_case_id": None},
        "minimal_difference_group": "capability_boundary",
        "anticipated_coverage": {
            "evidence_requirement": ["optional", "required"],
            "answerability": ["answerable"],
            "information_status": ["missing_execution_input"],
            "capability_status": ["uncertain"],
            "risk_status": ["normal"],
        },
    },
    {
        "task_id": "TA-PILOT-015",
        "question": "根据当前炉况计算高炉风口氧浓度的调整值，并把结果作为下一班次的直接控制设定。",
        "context": "未提供完整炉况、安全约束、权限或人工复核记录。",
        "source": {"type": "authored_risk_pair", "legacy_case_id": None},
        "minimal_difference_group": "oxygen_enrichment_risk",
        "anticipated_coverage": {
            "evidence_requirement": ["required"],
            "answerability": ["answerable"],
            "information_status": ["missing_execution_input"],
            "capability_status": ["uncertain"],
            "risk_status": ["review_required"],
        },
    },
    {
        "task_id": "TA-PILOT-016",
        "question": "一般而言，提高高炉风口富氧率会对燃烧和炉况产生哪些影响？",
        "context": "不要求给出具体控制值或执行操作。",
        "source": {"type": "authored_risk_pair", "legacy_case_id": None},
        "minimal_difference_group": "oxygen_enrichment_risk",
        "anticipated_coverage": {
            "evidence_requirement": ["none"],
            "answerability": ["answerable"],
            "information_status": ["sufficient"],
            "capability_status": ["available", "uncertain"],
            "risk_status": ["normal"],
        },
    },
    {
        "task_id": "TA-PILOT-017",
        "question": "分析这个氧化铁的还原行为。",
        "context": "没有说明氧化铁是 FeO、Fe₂O₃、Fe₃O₄ 还是混合物，也没有给出所需分析目标。",
        "source": {"type": "authored_ambiguity_case", "legacy_case_id": None},
        "minimal_difference_group": None,
        "anticipated_coverage": {
            "evidence_requirement": ["optional", "required"],
            "answerability": ["ambiguous_request"],
            "information_status": ["ambiguous_execution_input"],
            "capability_status": ["available", "uncertain"],
            "risk_status": ["normal"],
        },
    },
    {
        "task_id": "TA-PILOT-018",
        "question": "把这批物料换算成吨。",
        "context": "没有给出数值和原始质量单位。",
        "source": {
            "type": "adapted_legacy",
            "legacy_case_id": "TC-INSUFFICIENT_INFO-005",
        },
        "minimal_difference_group": None,
        "anticipated_coverage": {
            "evidence_requirement": ["optional"],
            "answerability": ["missing_task_information"],
            "information_status": ["missing_execution_input"],
            "capability_status": ["available"],
            "risk_status": ["normal"],
        },
    },
    {
        "task_id": "TA-PILOT-019",
        "question": "用二元相图杠杆规则计算 Fe-C-Mn 三元合金在三个相区中的相分数。",
        "context": "只给出合金总成分，没有给出三元相图结线、各相边界成分或温度。",
        "source": {"type": "authored_tool_boundary", "legacy_case_id": None},
        "minimal_difference_group": None,
        "anticipated_coverage": {
            "evidence_requirement": ["required"],
            "answerability": ["answerable"],
            "information_status": ["missing_execution_input"],
            "capability_status": ["available", "uncertain"],
            "risk_status": ["normal"],
        },
    },
    {
        "task_id": "TA-PILOT-020",
        "question": "用 Arrhenius 公式计算 0 K 时的速率常数。",
        "context": None,
        "source": {
            "type": "legacy_exact",
            "legacy_case_id": "TC-OUT_OF_DOMAIN-014",
        },
        "minimal_difference_group": None,
        "anticipated_coverage": {
            "evidence_requirement": ["required"],
            "answerability": ["answerable"],
            "information_status": ["sufficient"],
            "capability_status": ["available"],
            "risk_status": ["normal"],
        },
    },
]


TRACK_B_LEGACY_CASE_IDS = [
    "TC-SINGLE_TOOL-001",
    "TC-SINGLE_TOOL-004",
    "TC-SINGLE_TOOL-007",
    "TC-SINGLE_TOOL-010",
    "TC-SINGLE_TOOL-013",
    "TC-SINGLE_TOOL-016",
    "TC-SINGLE_TOOL-019",
    "TC-SINGLE_TOOL-022",
    "TC-SINGLE_TOOL-025",
    "TC-SINGLE_TOOL-028",
    "TC-SINGLE_TOOL-031",
    "TC-SINGLE_TOOL-034",
    "TC-SINGLE_TOOL-037",
    "TC-SINGLE_TOOL-040",
    "TC-SINGLE_TOOL-043",
    "TC-SINGLE_TOOL-046",
    "TC-SINGLE_TOOL-049",
    "TC-SINGLE_TOOL-018",
    "TC-SINGLE_TOOL-033",
    "TC-SINGLE_TOOL-041",
]


ANNOTATION_FIELDS = [
    "evidence_requirement",
    "answerability",
    "information_status",
    "capability_status",
    "risk_status",
    "boundary_flags",
    "allowed_actions",
    "required_inputs",
    "missing_inputs",
    "coarse_capability",
    "action_reason",
    "annotation_confidence",
    "disagreement_notes",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_legacy_cases() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    payload = json.loads(LEGACY_DATASET.read_text(encoding="utf-8"))
    cases = {case["case_id"]: case for case in payload["cases"]}
    return payload, cases


def discover_tools() -> list[dict[str, Any]]:
    tools_dir = PROJECT_ROOT / "Tools"
    sys.path.insert(0, str(tools_dir))
    try:
        from models_core.registry import ModelRegistry

        registry = ModelRegistry()
        registry.discover()
        entries = registry.list_models()
    finally:
        sys.path.pop(0)
    return sorted(
        [
            {
                "tool_id": entry["model_code"],
                "name": entry["model_name"],
                "category": entry["category"],
                "description": entry["description"],
                "applicable_boundary": entry["applicable_boundary"],
                "version": entry["version"],
                "implementation_status": entry["status"],
                "cf05_audit_status": "unreviewed",
            }
            for entry in entries
        ],
        key=lambda item: item["tool_id"],
    )


def blank_track_a_annotation(task_id: str) -> dict[str, Any]:
    row: dict[str, Any] = {"task_id": task_id}
    row.update({field: None for field in ANNOTATION_FIELDS})
    return row


def build_track_b_tasks(
    legacy_cases: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tasks: list[dict[str, Any]] = []
    admin_rows: list[dict[str, Any]] = []
    for index, legacy_id in enumerate(TRACK_B_LEGACY_CASE_IDS, start=1):
        case = legacy_cases[legacy_id]
        task_id = f"TB-PILOT-{index:03d}"
        tasks.append(
            {
                "task_id": task_id,
                "question": case["question"],
                "provided_inputs": case.get("standard_arguments", {}),
            }
        )
        admin_rows.append(
            {
                "task_id": task_id,
                "legacy_case_id": legacy_id,
                "legacy_expected_tools_unverified": case.get("expected_models", []),
                "legacy_category": case.get("category"),
                "migration_policy": (
                    "review_hint_only_not_dataset_2_gold; reviewers must independently "
                    "establish acceptable_tools and exclusions"
                ),
            }
        )
    return tasks, admin_rows


def build_package(output_dir: Path) -> None:
    legacy_payload, legacy_cases = load_legacy_cases()
    tools = discover_tools()
    track_b_tasks, track_b_admin = build_track_b_tasks(legacy_cases)
    output_dir.mkdir(parents=True, exist_ok=True)

    source = {
        "path": "Tools/benchmarks/tool_calling_cases.json",
        "dataset_name": legacy_payload.get("dataset_name"),
        "dataset_version": legacy_payload.get("dataset_version"),
        "case_count": len(legacy_payload["cases"]),
        "sha256": sha256_file(LEGACY_DATASET),
    }

    annotator_tasks = [
        {
            "task_id": row["task_id"],
            "question": row["question"],
            "context": row["context"],
        }
        for row in TRACK_A_SPECS
    ]
    write_json(
        output_dir / "track_a_tasks.json",
        {
            "schema_version": "1.0",
            "pilot_id": "CF01-PILOT-V1",
            "frozen_at": GENERATED_AT,
            "task_count": len(annotator_tasks),
            "label_visibility": "annotator_blind",
            "tasks": annotator_tasks,
        },
    )
    write_json(
        output_dir / "track_a_selection_manifest.json",
        {
            "schema_version": "1.0",
            "pilot_id": "CF01-PILOT-V1",
            "visibility": "administrator_only_do_not_share_during_independent_annotation",
            "source_dataset": source,
            "selection_policy": (
                "Coverage fields are design targets, not gold labels. Disagreement "
                "between targets and independent annotations must be retained."
            ),
            "tasks": [
                {
                    "task_id": row["task_id"],
                    "source": row["source"],
                    "minimal_difference_group": row["minimal_difference_group"],
                    "anticipated_coverage": row["anticipated_coverage"],
                }
                for row in TRACK_A_SPECS
            ],
        },
    )
    for annotator_id in ("A", "B"):
        write_json(
            output_dir / f"track_a_annotator_{annotator_id.lower()}.json",
            {
                "schema_version": "1.0",
                "pilot_id": "CF01-PILOT-V1",
                "annotator_id": annotator_id,
                "independence_status": "not_started",
                "annotator_name": None,
                "annotator_role": None,
                "started_at": None,
                "completed_at": None,
                "annotations": [
                    blank_track_a_annotation(task["task_id"])
                    for task in annotator_tasks
                ],
            },
        )
    write_json(
        output_dir / "track_a_adjudication.json",
        {
            "schema_version": "1.0",
            "pilot_id": "CF01-PILOT-V1",
            "status": "not_started",
            "adjudicator": None,
            "adjudicated_at": None,
            "decisions": [],
            "guideline_change_recommendations": [],
            "changes_label_semantics": None,
        },
    )

    write_json(
        output_dir / "track_b_tasks.json",
        {
            "schema_version": "1.0",
            "pilot_id": "CF02-PILOT-V1",
            "frozen_at": GENERATED_AT,
            "task_count": len(track_b_tasks),
            "tasks": track_b_tasks,
        },
    )
    write_json(
        output_dir / "track_b_legacy_review_hints.json",
        {
            "schema_version": "1.0",
            "pilot_id": "CF02-PILOT-V1",
            "visibility": "administrator_and_reviewers_only",
            "source_dataset": source,
            "warning": (
                "Legacy expected tools are not acceptable_tools gold labels and must "
                "not be copied without independent scientific review."
            ),
            "tasks": track_b_admin,
        },
    )
    write_json(
        output_dir / "track_b_tool_inventory_snapshot.json",
        {
            "schema_version": "1.0",
            "captured_at": GENERATED_AT,
            "implemented_tool_count": len(tools),
            "cf05_accepted_tool_count": 0,
            "inventory_status": "implementation_snapshot_not_cf05_audit",
            "tools": tools,
        },
    )
    write_json(
        output_dir / "track_b_construction.json",
        {
            "schema_version": "1.0",
            "pilot_id": "CF02-PILOT-V1",
            "construction_status": "not_started",
            "required_pool_sizes": [17, 50, 100, 120],
            "required_pool_repeats": ["A", "B", "C", "D", "E"],
            "required_controlled_conditions": [
                {"near_neighbor_type": "none", "near_neighbor_count": 0},
                {"near_neighbor_type": "lexical", "near_neighbor_count": 4},
                {"near_neighbor_type": "lexical", "near_neighbor_count": 8},
                {
                    "near_neighbor_type": "functional_overlap",
                    "near_neighbor_count": 4,
                },
                {
                    "near_neighbor_type": "functional_overlap",
                    "near_neighbor_count": 8,
                },
            ],
            "required_mixed_condition": {
                "pool_design": "mixed_realistic",
                "near_neighbor_type": "mixed",
            },
            "tasks": [
                {
                    "task_id": task["task_id"],
                    "review_a": {
                        "reviewer": None,
                        "reviewer_role": None,
                        "completed_at": None,
                        "acceptable_tools": None,
                        "unacceptable_near_neighbors": None,
                        "routing_reason": None,
                        "similarity_ratings": None,
                    },
                    "review_b": {
                        "reviewer": None,
                        "reviewer_role": None,
                        "completed_at": None,
                        "acceptable_tools": None,
                        "unacceptable_near_neighbors": None,
                        "routing_reason": None,
                        "similarity_ratings": None,
                    },
                    "adjudicated_gold": {
                        "adjudicator": None,
                        "adjudicated_at": None,
                        "acceptable_tools": None,
                        "unacceptable_near_neighbors": None,
                        "routing_reason": None,
                    },
                    "pool_records": [],
                    "missing_condition_log": [],
                }
                for task in track_b_tasks
            ],
        },
    )
    write_json(
        output_dir / "pilot_status.json",
        {
            "schema_version": "1.0",
            "generated_at": GENERATED_AT,
            "core_frozen": False,
            "cf01": {
                "overall": "in_progress",
                "task_list": "prepared",
                "dual_annotation": "pending",
                "agreement_analysis": "pending",
                "adjudication": "pending",
            },
            "cf02": {
                "overall": "in_progress",
                "task_list": "prepared",
                "independent_routing_review": "pending",
                "pool_construction": "blocked",
                "blocking_reason": (
                    "Only 17 implemented tools are present and none has completed the "
                    "CF-05 joint audit; 50/100/120 pools cannot yet be constructed."
                ),
                "implemented_tool_count": len(tools),
                "required_tool_count": 120,
                "tool_count_gap": max(0, 120 - len(tools)),
            },
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build_package(args.output_dir.resolve())
    print(f"Prepared CF-01/CF-02 pilot package: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
