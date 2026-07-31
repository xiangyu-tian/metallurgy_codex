"""Build the local-only E2 hybrid gate candidate and audit package."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parents[1]
PROJECT_ROOT = HERE.parents[2]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from core_freeze.e2_contract_boundaries.build_e2_pilot_v2 import (  # noqa: E402
    reference_semantic_flags,
)
from core_freeze.e2_contract_boundaries.hybrid_gate_v1 import (  # noqa: E402
    derive_structural_flags,
    run_hybrid_gate,
)


V1_TASKS_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_pilot_20260731"
    / "e2_pilot_tasks.json"
)
V2_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_pilot_v2_observable_candidate_20260731"
)
V2_TASKS_PATH = V2_DIR / "e2_pilot_tasks_v2.json"
V2_MANIFEST_PATH = V2_DIR / "artifact_manifest.json"
CONTRACTS_PATH = HERE.parent / "verified_core" / "contracts_v1.json"
BASE_POLICY_PATH = HERE / "policy_v1.json"
HYBRID_POLICY_PATH = HERE / "hybrid_gate_policy_v1.json"
SEMANTIC_PROMPT_PATH = HERE / "prompts_hybrid_semantic_v1.json"
SEMANTIC_SCHEMA_PATH = HERE / "output_schema_hybrid_semantic_v1.json"
GATE_PATH = HERE / "hybrid_gate_v1.py"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expected_subset(
    task: dict[str, Any],
    allowed: set[str],
) -> list[str]:
    return [flag for flag in task["expected_flags"] if flag in allowed]


def audit_v1_observability(
    *,
    contracts: dict[str, dict[str, Any]],
    hybrid_policy: dict[str, Any],
) -> dict[str, Any]:
    tasks = load_json(V1_TASKS_PATH)["tasks"]
    structural_allowed = set(hybrid_policy["structural_flags"])
    mismatches = []
    for task in tasks:
        observed = derive_structural_flags(
            task["structured_state"],
            contracts[task["source_tool_id"]],
            hybrid_policy,
        )
        expected = _expected_subset(task, structural_allowed)
        if set(observed) != set(expected):
            mismatches.append(
                {
                    "task_id": task["task_id"],
                    "mutation_types": task["mutation_types"],
                    "expected_structural_flags": expected,
                    "observable_structural_flags": observed,
                    "defect": (
                        "gold structural flag is not derivable from the "
                        "final model-visible structured_state"
                    ),
                }
            )
    return {
        "schema_version": "1.0",
        "audit_id": "E2-V1-LABEL-OBSERVABILITY-DEFECT-20260731",
        "source_dataset_id": load_json(V1_TASKS_PATH)["dataset_id"],
        "task_count": len(tasks),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "status": "defect_confirmed" if mismatches else "no_defect",
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }


def run_offline_integration(
    *,
    tasks: list[dict[str, Any]],
    contracts: dict[str, dict[str, Any]],
    base_policy: dict[str, Any],
    hybrid_policy: dict[str, Any],
    semantic_schema: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    structural_allowed = set(hybrid_policy["structural_flags"])
    semantic_allowed = set(hybrid_policy["semantic_flags"])
    records = []
    for task in tasks:
        contract = contracts[task["source_tool_id"]]
        oracle_semantic = _expected_subset(task, semantic_allowed)
        result = run_hybrid_gate(
            structured_state=task["structured_state"],
            contract=contract,
            semantic_output={"semantic_flags": oracle_semantic},
            base_policy=base_policy,
            hybrid_policy=hybrid_policy,
            semantic_schema=semantic_schema,
        )
        expected_structural = _expected_subset(
            task,
            structural_allowed,
        )
        records.append(
            {
                "task_id": task["task_id"],
                "source_tool_id": task["source_tool_id"],
                "mutation_types": task["mutation_types"],
                "expected_structural_flags": expected_structural,
                "derived_structural_flags": result["structural_flags"],
                "oracle_semantic_flags": oracle_semantic,
                "merged_flags": result["merged_flags"],
                "expected_flags": task["expected_flags"],
                "expected_action": task["policy_expected_action"],
                "derived_action": result["policy_expected_action"],
                "structural_exact": (
                    set(result["structural_flags"])
                    == set(expected_structural)
                ),
                "merged_exact": (
                    set(result["merged_flags"])
                    == set(task["expected_flags"])
                ),
                "action_correct": (
                    result["policy_expected_action"]
                    == task["policy_expected_action"]
                ),
                "semantic_source": "oracle_for_pipeline_test_only",
                "model_performance_claim_allowed": False,
            }
        )
    count = len(records)
    return records, {
        "schema_version": "1.0-candidate",
        "analysis_type": "offline_oracle_semantic_pipeline_test",
        "task_count": count,
        "structural_exact_count": sum(
            row["structural_exact"] for row in records
        ),
        "structural_exact_accuracy": (
            sum(row["structural_exact"] for row in records) / count
        ),
        "merged_exact_count": sum(row["merged_exact"] for row in records),
        "merged_exact_accuracy": (
            sum(row["merged_exact"] for row in records) / count
        ),
        "action_correct_count": sum(
            row["action_correct"] for row in records
        ),
        "action_accuracy": (
            sum(row["action_correct"] for row in records) / count
        ),
        "oracle_semantic_flags_used": True,
        "external_api_calls": 0,
        "model_performance_claim_allowed": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }


def validate_candidate_inputs() -> dict[str, Any]:
    v2 = load_json(V2_TASKS_PATH)
    contracts_doc = load_json(CONTRACTS_PATH)
    contracts = {
        row["tool_id"]: row for row in contracts_doc["contracts"]
    }
    base_policy = load_json(BASE_POLICY_PATH)
    hybrid_policy = load_json(HYBRID_POLICY_PATH)
    semantic_prompt = load_json(SEMANTIC_PROMPT_PATH)
    semantic_schema = load_json(SEMANTIC_SCHEMA_PATH)
    if hybrid_policy["external_api_execution_authorized"] is not False:
        raise ValueError("hybrid candidate must not authorize API execution")
    if semantic_prompt["external_api_execution_authorized"] is not False:
        raise ValueError("semantic prompt must not authorize API execution")
    if set(semantic_schema["properties"]) != {"semantic_flags"}:
        raise ValueError("semantic schema exposes non-semantic fields")
    prompt_text = json.dumps(semantic_prompt, ensure_ascii=False)
    for forbidden in ("mutation_types", "expected_flags", "task_id"):
        if forbidden in prompt_text:
            raise ValueError(f"semantic prompt leaks {forbidden}")
    if v2["task_count"] != 55:
        raise ValueError("hybrid candidate expects 55 v2 tasks")
    return {
        "v2": v2,
        "contracts": contracts,
        "base_policy": base_policy,
        "hybrid_policy": hybrid_policy,
        "semantic_prompt": semantic_prompt,
        "semantic_schema": semantic_schema,
    }


def build_package(output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    values = validate_candidate_inputs()
    defect = audit_v1_observability(
        contracts=values["contracts"],
        hybrid_policy=values["hybrid_policy"],
    )
    records, integration = run_offline_integration(
        tasks=values["v2"]["tasks"],
        contracts=values["contracts"],
        base_policy=values["base_policy"],
        hybrid_policy=values["hybrid_policy"],
        semantic_schema=values["semantic_schema"],
    )
    if defect["mismatch_count"] != 4:
        raise ValueError("expected four confirmed v1 observability defects")
    if integration["structural_exact_accuracy"] != 1.0:
        raise ValueError("deterministic structural layer is not exact")
    if integration["merged_exact_accuracy"] != 1.0:
        raise ValueError("offline hybrid merge pipeline is not exact")
    output_dir.mkdir(parents=True)
    snapshots = {
        HYBRID_POLICY_PATH: output_dir / "hybrid_policy_snapshot.json",
        SEMANTIC_PROMPT_PATH: (
            output_dir / "semantic_prompt_snapshot.json"
        ),
        SEMANTIC_SCHEMA_PATH: (
            output_dir / "semantic_schema_snapshot.json"
        ),
        GATE_PATH: output_dir / "hybrid_gate_snapshot.py",
    }
    for source, target in snapshots.items():
        shutil.copyfile(source, target)
    defect_path = output_dir / "v1_observability_defect_report.json"
    defect_path.write_text(
        json.dumps(defect, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    records_path = output_dir / "offline_pipeline_records.jsonl"
    with records_path.open("x", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )
    integration_path = output_dir / "offline_pipeline_report.json"
    integration_path.write_text(
        json.dumps(integration, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = {
        "schema_version": "1.0-candidate",
        "candidate_id": "E2-HYBRID-BOUNDARY-GATE-V1-20260731",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "local_candidate_prepared_not_authorized",
        "source_dataset_id": values["v2"]["dataset_id"],
        "v1_observability_defect_count": defect["mismatch_count"],
        "offline_pipeline": integration,
        "responsibility_split": {
            "deterministic_structural_layer": values["hybrid_policy"][
                "structural_flags"
            ],
            "llm_semantic_layer": values["hybrid_policy"][
                "semantic_flags"
            ],
            "merge": values["hybrid_policy"]["merge_rule"],
            "decision": values["hybrid_policy"]["decision_rule"],
        },
        "limitations": [
            "semantic flags are oracle inputs in the offline pipeline test",
            "no model performance has been measured on v2 tasks",
            "v2 tasks are development candidates, not a held-out set",
            "temperature, pressure and model-card OOD remain uncovered",
        ],
        "external_api_calls": 0,
        "external_api_execution_authorized": False,
        "model_performance_claim_allowed": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    report_path = output_dir / "candidate_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    artifacts = list(snapshots.values()) + [
        defect_path,
        records_path,
        integration_path,
        report_path,
    ]
    manifest = {
        "schema_version": "1.0-candidate",
        "candidate_id": report["candidate_id"],
        "source_bindings": {
            "v1_tasks_sha256": file_hash(V1_TASKS_PATH),
            "v2_tasks_sha256": file_hash(V2_TASKS_PATH),
            "v2_manifest_sha256": file_hash(V2_MANIFEST_PATH),
            "contracts_sha256": file_hash(CONTRACTS_PATH),
            "base_policy_sha256": file_hash(BASE_POLICY_PATH),
            "builder_sha256": file_hash(Path(__file__)),
        },
        "artifacts": [
            {"filename": path.name, "sha256": file_hash(path)}
            for path in artifacts
        ],
        "external_api_calls": 0,
        "external_api_execution_authorized": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    (output_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = build_package(args.output_dir.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
