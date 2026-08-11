"""Build the no-API CF-05 development-method decision candidate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common  # noqa: E402


CONFIG_PATH = Path(__file__).with_name("cf05_development_decision_config_v1.json")


def validate_config(config: dict[str, Any]) -> None:
    if config["decision_status"] != "candidate_pending_project_owner_adoption":
        raise ValueError("decision candidate must remain unadopted")
    if config["recommended_decision"] != "freeze_current_method_candidates_and_stop_taskset_specific_tuning":
        raise ValueError("recommended decision changed")
    if config["methods"] != ["full_schema", "lexical_top5", "dense_top5", "hierarchical"]:
        raise ValueError("method set changed")
    for field in (
        "external_api_calls_authorized",
        "independent_validation_split_access_allowed",
        "confirmatory_inference_allowed",
        "core_frozen",
    ):
        if config[field] is not False:
            raise ValueError(f"{field} must remain false")
    if config["cf05_status"] != "in_progress":
        raise ValueError("candidate package cannot pass CF-05")


def build(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    paths = {
        name: common.validate_binding(binding)
        for name, binding in config["bindings"].items()
    }
    data = {
        name: common.load_json(path)
        for name, path in paths.items()
        if path.suffix.lower() == ".json"
    }
    a003 = data["a003_analysis"]
    a004 = data["a004_volatility"]
    postgate = data["a004_postgate"]
    multitarget = data["multitarget_analysis"]
    variability = data["a002_a003_variability"]
    if a003["overall"]["complete_call_accuracy"] != 1.0:
        raise ValueError("A003 pipeline evidence changed")
    if a004["pairing_summary"]["exact_three_repeat_agreement_rate"] != 1.0:
        raise ValueError("A004 repeat evidence changed")
    if postgate["gate_false_block_count"] != 0:
        raise ValueError("A004 postgate false-block evidence changed")
    if multitarget["overall"]["complete_call_accuracy"] != 1:
        raise ValueError("multi-target development evidence changed")
    if variability["matched_unit_count"] != 192:
        raise ValueError("A002/A003 variability evidence changed")
    if variability["variable_correctness_rate"] > 0.05:
        raise ValueError("A002/A003 variability exceeds candidate threshold")

    method_manifest = []
    method_bindings = {
        "full_schema": ["full_schema_config", "transport_policy"],
        "lexical_top5": ["lexical_config", "lexical_source", "transport_policy"],
        "dense_top5": [
            "dense_config",
            "dense_query_policy",
            "dense_source",
            "transport_policy",
        ],
        "hierarchical": [
            "hierarchical_config",
            "hierarchical_source",
            "lexical_config",
            "lexical_source",
            "transport_policy",
        ],
    }
    for method, names in method_bindings.items():
        method_manifest.append(
            {
                "method": method,
                "top_k": None if method == "full_schema" else config["top_k"],
                "artifacts": [
                    {
                        "role": name,
                        "path": config["bindings"][name]["path"],
                        "sha256": config["bindings"][name]["sha256"],
                    }
                    for name in names
                ],
                "candidate_freeze_action": "freeze_after_project_owner_adoption",
                "taskset_specific_retuning_allowed_after_adoption": False,
            }
        )

    evidence_matrix = [
        {
            "evidence_id": "E3-A003-CONTROLLED-PIPELINE",
            "scope": "single target; 0/8 neighbor conditions; 17/120 tools; four methods",
            "cells": a003["result_count"],
            "primary_observation": "complete_call_accuracy=1.0; ceiling observed",
            "allowed_use": "pipeline and scoring validation",
            "confirmatory_use": False,
        },
        {
            "evidence_id": "E3-MULTITARGET-MIXED-R2",
            "scope": "A001/A002/A004/B019; mixed realistic; 17/120 tools; four methods",
            "cells": multitarget["result_count"],
            "primary_observation": "complete_call_accuracy=1.0; ceiling observed",
            "allowed_use": "multi-target execution validation",
            "confirmatory_use": False,
        },
        {
            "evidence_id": "E3-A004-HARDCASE-R1-R3",
            "scope": "A004 hard cases; three repeats",
            "cells": a004["all_repeat_cell_count"],
            "primary_observation": "47/48 stable correct; 1/48 stable multi-call failure",
            "allowed_use": "local failure reproducibility and volatility estimation",
            "confirmatory_use": False,
        },
        {
            "evidence_id": "E3-A002-A003-TOP5-R1-R3",
            "scope": "16 minimal-difference tasks; 17/120 tools; three Top-5 methods; three repeats",
            "cells": variability["result_count"],
            "primary_observation": "186/192 stable correct; 2 stable failures; 4 variable units",
            "allowed_use": "Top-5 stability and residual-risk localization",
            "confirmatory_use": False,
        },
        {
            "evidence_id": "E3-A004-POSTGATE-PROBES",
            "scope": "10 new development probes",
            "cells": postgate["task_count"],
            "primary_observation": "10/10 correct; zero false block",
            "allowed_use": "gate safety check only",
            "confirmatory_use": False,
        },
    ]

    risks = [
        {
            "risk_id": "CF05-RISK-001",
            "severity": "material_local",
            "description": "Equivalent or overlapping endpoints can elicit multiple tool calls on complex chemistry requests at 120-tool scale.",
            "evidence": "A004 has one stable three-repeat multi-call unit; A002/A003 has two stable and four variable units, all localized to complex requests.",
            "treatment": "Retain as intention-to-treat failure; do not post-hoc choose one call; disclose and test on independent data.",
            "blocks_method_candidate_freeze": False,
            "blocks_cf05_overall_pass": False,
        },
        {
            "risk_id": "CF05-RISK-002",
            "severity": "design_blocker",
            "description": "The full five-target formal 0/4/8 controlled-neighbor matrix is not yet evidenced as complete.",
            "evidence": "A003 has the complete controlled slice; other targets provide mixed and partial hard-case slices.",
            "treatment": "Complete a no-leakage pool-coverage audit before CF-05 can be marked passed.",
            "blocks_method_candidate_freeze": False,
            "blocks_cf05_overall_pass": True,
        },
        {
            "risk_id": "CF05-RISK-003",
            "severity": "inference_limitation",
            "description": "Several development slices show ceiling performance and cannot discriminate routing methods.",
            "evidence": "A003 and four-target mixed-realistic slices both achieved 100% across methods.",
            "treatment": "Do not tune further on these tasks; use frozen independent validation for method comparison.",
            "blocks_method_candidate_freeze": False,
            "blocks_cf05_overall_pass": False,
        },
        {
            "risk_id": "CF05-RISK-004",
            "severity": "external_validity",
            "description": "Only five tools are verified executable while the remaining catalog entries primarily provide frozen Schema-level routing distractors.",
            "evidence": "Current v1.1 catalog governance distinguishes verified executables from Schema-only entries.",
            "treatment": "Limit claims to routing-scale evidence and verified-core execution; do not call all 120 entries validated engines.",
            "blocks_method_candidate_freeze": False,
            "blocks_cf05_overall_pass": False,
        },
    ]

    decision = {
        "schema_version": "1.0",
        "decision_id": config["decision_id"],
        "decision_status": config["decision_status"],
        "recommended_decision": config["recommended_decision"],
        "recommendation_basis": {
            "method_pipeline_operational": True,
            "three_repeat_variability_below_5_percent": True,
            "failures_localized_and_auditable": True,
            "further_taskset_specific_tuning_risk": "development_overfitting",
        },
        "candidate_actions_after_adoption": [
            "freeze the four method definitions and transport policy by SHA-256",
            "prohibit further tuning on consumed development tasks",
            "retain all multi-call and provider failures as ITT errors",
            "run the remaining no-leakage CF-05 pool-coverage audit",
            "keep the independent validation split closed until its separate opening gate",
        ],
        "not_authorized_by_this_candidate": [
            "external API execution",
            "independent validation access",
            "confirmatory H3/H4 inference",
            "CF-05 passed status",
            "core_frozen=true",
        ],
        "cf05_status": "in_progress",
        "core_frozen": False,
        "next_gate": "project owner adoption of this method-freeze recommendation, followed by a deterministic five-target 0/4/8 pool-coverage audit",
    }
    report = {
        "schema_version": "1.0",
        "decision_id": config["decision_id"],
        "status": "decision_candidate_complete_pending_project_owner_adoption",
        "method_count": len(method_manifest),
        "evidence_record_count": len(evidence_matrix),
        "residual_risk_count": len(risks),
        "cf05_overall_blocker_count": sum(row["blocks_cf05_overall_pass"] for row in risks),
        "external_api_calls": 0,
        "independent_validation_split_accessed": False,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
    }
    return {
        "decision": decision,
        "method_manifest": method_manifest,
        "evidence_matrix": evidence_matrix,
        "risks": risks,
        "report": report,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = common.load_json(CONFIG_PATH)
    result = build(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "cf05_development_decision_config_snapshot.json": config,
        "cf05_development_method_freeze_candidate.json": result["decision"],
        "cf05_method_artifact_manifest.json": {
            "schema_version": "1.0",
            "methods": result["method_manifest"],
        },
        "cf05_development_evidence_matrix.json": {
            "schema_version": "1.0",
            "records": result["evidence_matrix"],
        },
        "cf05_residual_risk_register.json": {
            "schema_version": "1.0",
            "risks": result["risks"],
        },
        "cf05_development_decision_report.json": result["report"],
    }
    for filename, value in artifacts.items():
        common.write_json(output_dir / filename, value)
    paths = sorted(output_dir.iterdir(), key=lambda path: path.name)
    common.write_json(
        output_dir / "artifact_manifest.json",
        {
            "schema_version": "1.0",
            "decision_id": config["decision_id"],
            "artifact_count": len(paths),
            "artifacts": [
                {
                    "filename": path.name,
                    "sha256": common.file_hash(path),
                    "bytes": path.stat().st_size,
                }
                for path in paths
            ],
        },
    )
    return result["report"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else WORKSPACE / args.output_dir
    print(json.dumps(build_outputs(output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
