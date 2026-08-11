"""Build and validate an A002/A003 family-governance candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common


CONFIG_PATH = Path(__file__).with_name("a002_a003_family_governance_config_v1.json")


def validate_config(config: dict[str, Any]) -> None:
    if set(config["member_tool_ids"]) != {"A002", "A003"}:
        raise ValueError("family membership must remain A002/A003")
    if config["relation_type"] != "asymmetric_output_overlap":
        raise ValueError("relation type must match the frozen overlap audit")
    if config["primary_selection_metric"] != "primary_acceptable_tool_selection_accuracy":
        raise ValueError("primary selection metric cannot be changed by this governance candidate")
    if config["h3_symmetric_neighbor_eligibility"] is not False:
        raise ValueError("asymmetric pair cannot enter symmetric H3 near-neighbor gold")
    for field in (
        "local_tool_execution_allowed",
        "external_api_calls_allowed",
        "formal_catalog_mutation_allowed",
        "formal_gold_mutation_allowed",
        "protocol_mutation_allowed",
        "confirmatory_inference_allowed",
        "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")


def classify_case(*, task_primary_tool: str, selected_tool: str,
                  primary_tools: set[str], alternative_tools: set[str],
                  family_members: set[str]) -> dict[str, Any]:
    primary = selected_tool in primary_tools
    family = task_primary_tool in family_members and selected_tool in family_members
    alternative = not primary and selected_tool in alternative_tools
    scientific = primary or alternative
    return {
        "task_primary_tool": task_primary_tool,
        "selected_tool": selected_tool,
        "primary_selection_correct": primary,
        "tool_family_selection_correct": family,
        "alternative_success": alternative,
        "scientific_success_including_alternatives": scientific,
        "error_class": (
            "none_primary_success"
            if primary
            else "endpoint_preference_only"
            if family and alternative
            else "same_family_scientific_failure"
            if family
            else "alternative_success_outside_family"
            if alternative
            else "scientific_selection_failure"
        ),
    }


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {name: common.validate_binding(binding) for name, binding in config["bindings"].items()}
    overlap = common.load_json(paths["overlap_report"])
    relation = common.load_json(paths["relation_candidate"])
    rc2 = common.load_json(paths["rc2_task_candidate"])
    scored = common.load_json(paths["a003_scored_cells"])
    prior_report = common.load_json(paths["a003_analysis_report"])

    if overlap["a002_alternative_success_count"] != overlap["task_count"] or overlap["task_count"] != 12:
        raise ValueError("overlap evidence does not support the governance candidate")
    if overlap["a002_primary_direct_acceptable_count"] != 0:
        raise ValueError("primary policy unexpectedly changed")
    if relation["relation_type"] != config["relation_type"]:
        raise ValueError("relation evidence does not match governance config")
    if len(rc2["tasks"]) != 12 or any("A002" not in row["alternative_success_tools_rc2_candidate"] for row in rc2["tasks"]):
        raise ValueError("rc2 candidate does not consistently report A002 alternative success")

    family_members = set(config["member_tool_ids"])
    decision_table = [
        {
            "case_id": "A003-TASK-SELECT-A003",
            **classify_case(
                task_primary_tool="A003", selected_tool="A003", primary_tools={"A003"},
                alternative_tools={"A002"}, family_members=family_members,
            ),
        },
        {
            "case_id": "A003-TASK-SELECT-A002",
            **classify_case(
                task_primary_tool="A003", selected_tool="A002", primary_tools={"A003"},
                alternative_tools={"A002"}, family_members=family_members,
            ),
        },
        {
            "case_id": "A002-TASK-SELECT-A002",
            **classify_case(
                task_primary_tool="A002", selected_tool="A002", primary_tools={"A002"},
                alternative_tools=set(), family_members=family_members,
            ),
        },
        {
            "case_id": "A002-TASK-SELECT-A003",
            **classify_case(
                task_primary_tool="A002", selected_tool="A003", primary_tools={"A002"},
                alternative_tools=set(), family_members=family_members,
            ),
        },
        {
            "case_id": "A003-TASK-SELECT-UNRELATED",
            **classify_case(
                task_primary_tool="A003", selected_tool="B019", primary_tools={"A003"},
                alternative_tools={"A002"}, family_members=family_members,
            ),
        },
    ]

    existing_rows = scored["rows"]
    if len(existing_rows) != 96:
        raise ValueError("unexpected A003 development result count")
    rc2_tasks = {row["task_id"]: row for row in rc2["tasks"]}
    reclassified = []
    for row in existing_rows:
        task = rc2_tasks[row["task_id"]]
        selected = row["selected_tool_id"]
        metrics = classify_case(
            task_primary_tool="A003",
            selected_tool=selected,
            primary_tools=set(task["primary_acceptable_tools_rc2_candidate"]),
            alternative_tools=set(task["alternative_success_tools_rc2_candidate"]),
            family_members=family_members,
        )
        reclassified.append({"cell_id": row["cell_id"], "task_id": row["task_id"], **metrics})

    policy = {
        "schema_version": "1.0",
        "governance_id": config["governance_id"],
        "status": "candidate_pending_project_approval",
        "family_id": config["family_id"],
        "members": [
            {"tool_id": "A002", "role": "parser_superset", "primary_task_output": "elements"},
            {"tool_id": "A003", "role": "dedicated_molar_mass_view", "primary_task_output": "molar_mass_with_unit"},
        ],
        "relation_type": config["relation_type"],
        "counting": {
            "callable_endpoint_count": 2,
            "family_deduplicated_capability_count": 1,
            "h4_primary_scale_axis": config["h4_primary_scale_axis"],
            "h4_companion_scale_axis": config["h4_companion_scale_axis"],
            "rule": (
                "Keep both schemas when measuring routing load; deduplicate the family when claiming independent "
                "scientific capability count."
            ),
        },
        "metrics": {
            "primary": config["primary_selection_metric"],
            "secondary": config["secondary_metrics"],
            "primary_support_may_be_changed_by_secondary_metrics": False,
        },
        "h3": {
            "eligible_as_symmetric_functional_neighbor_pair": False,
            "allowed_role": "asymmetric_overlap_secondary_analysis",
        },
        "task_policy": {
            "a002_element_tasks": {"primary": ["A002"], "a003_alternative": False},
            "a003_molar_mass_tasks": {"primary": "task_specific_frozen_set", "a002_alternative": True},
        },
        "formal_catalog_mutated": False,
        "formal_gold_mutated": False,
        "protocol_mutated": False,
        "core_frozen": False,
    }

    existing_primary = sum(row["primary_selection_correct"] for row in reclassified)
    existing_family = sum(row["tool_family_selection_correct"] for row in reclassified)
    existing_alternative = sum(row["alternative_success"] for row in reclassified)
    existing_scientific = sum(row["scientific_success_including_alternatives"] for row in reclassified)
    report = {
        "schema_version": "1.0",
        "governance_id": config["governance_id"],
        "status": "development_governance_candidate_built",
        "evidence_task_count": overlap["task_count"],
        "decision_table_case_count": len(decision_table),
        "existing_a003_cell_count": len(reclassified),
        "existing_primary_success_count": existing_primary,
        "existing_family_success_count": existing_family,
        "existing_alternative_success_count": existing_alternative,
        "existing_scientific_success_count": existing_scientific,
        "existing_primary_accuracy_unchanged": (
            existing_primary == len(reclassified)
            and prior_report["overall"]["acceptable_tool_selection_accuracy"] == 1.0
        ),
        "endpoint_count_for_a002_a003": 2,
        "family_deduplicated_capability_count": 1,
        "h3_symmetric_neighbor_eligibility": False,
        "formal_catalog_mutated": False,
        "formal_gold_mutated": False,
        "protocol_mutated": False,
        "external_api_calls": 0,
        "tool_calls_executed": 0,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "next_gate": "project approval of family governance before minimal-pair task generation",
    }
    return {
        "policy": policy,
        "decision_table": decision_table,
        "reclassified": reclassified,
        "report": report,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = common.load_json(CONFIG_PATH)
    result = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a002_a003_family_governance_config_snapshot.json": config,
        "a002_a003_family_governance_candidate.json": result["policy"],
        "a002_a003_metric_decision_table.json": {
            "schema_version": "1.0", "rows": result["decision_table"]
        },
        "a003_existing_results_governance_reclassification.json": {
            "schema_version": "1.0", "rows": result["reclassified"]
        },
        "a002_a003_family_governance_report.json": result["report"],
    }
    for filename, value in artifacts.items():
        common.write_json(output_dir / filename, value)
    artifact_paths = list(output_dir.iterdir())
    common.write_json(output_dir / "artifact_manifest.json", {
        "schema_version": "1.0",
        "governance_id": config["governance_id"],
        "artifact_count": len(artifact_paths),
        "artifacts": [
            {"filename": path.name, "sha256": common.file_hash(path), "bytes": path.stat().st_size}
            for path in sorted(artifact_paths, key=lambda item: item.name)
        ],
    })
    return result["report"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else common.WORKSPACE / args.output_dir
    report = build_outputs(output_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
