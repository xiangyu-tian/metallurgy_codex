"""Run the offline A004 contract-gate boundary challenge set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from Tools.core_freeze.e3_routing import a004_contract_adjudication as gate


CHALLENGE_PATH = Path(__file__).with_name("a004_contract_adjudication_challenge_v1.json")


def validate_challenge(challenge: dict[str, Any]) -> None:
    for field in ("gold_access_allowed_during_decision", "external_api_calls_authorized",
                  "tool_execution_allowed"):
        if challenge[field] is not False:
            raise ValueError(f"{field} must remain false")
    case_ids = [row["case_id"] for row in challenge["cases"]]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("challenge case ids must be unique")
    if len(case_ids) < 15:
        raise ValueError("challenge set must contain at least 15 cases")


def run_challenge(challenge: dict[str, Any], profiles: dict[str, Any]) -> dict[str, Any]:
    validate_challenge(challenge)
    rows = []
    for case in challenge["cases"]:
        # Only the input envelope enters the decision function. Expected outcomes are
        # read after adjudication and are used solely for offline challenge scoring.
        decision_input = case["input"]
        decision = gate.adjudicate(
            decision_input["problem_text"], decision_input["raw_response"], profiles
        )
        expected = case["expected"]
        checks = {
            "decision_matches": decision["decision"] == expected["decision"],
            "selected_tool_matches": decision["selected_tool_id"] == expected["selected_tool_id"],
            "selected_arguments_match": (
                "selected_arguments" not in expected
                or decision["selected_arguments"] == expected["selected_arguments"]
            ),
        }
        rows.append({
            "case_id": case["case_id"],
            "category": case["category"],
            "decision_input_fields": sorted(decision_input),
            "expected_accessed_after_decision": True,
            "decision": decision,
            "expected": expected,
            "checks": checks,
            "passed": all(checks.values()),
        })
    passed = sum(row["passed"] for row in rows)
    report = {
        "schema_version": "1.0",
        "challenge_id": challenge["challenge_id"],
        "analysis_status": "offline_boundary_challenge_complete",
        "case_count": len(rows),
        "passed_count": passed,
        "failed_count": len(rows) - passed,
        "pass_rate": passed / len(rows),
        "gold_accessed_during_decision": False,
        "expected_outcomes_used_after_decision_only": True,
        "external_api_calls": 0,
        "tool_calls_executed": 0,
        "independent_model_validation_claim_allowed": False,
        "confirmatory_inference_allowed": False,
        "cf05_status": "in_progress",
        "core_frozen": False,
        "interpretation": "developer-authored boundary challenge validates conservative rule behavior, not model generalization",
    }
    return {"rows": rows, "report": report}


def build_outputs(output_dir: Path) -> dict[str, Any]:
    challenge = gate.load_json(CHALLENGE_PATH)
    config = gate.load_json(gate.CONFIG_PATH)
    profiles = gate.load_bound_profile_registry(config)
    result = run_challenge(challenge, profiles)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "a004_contract_gate_challenge_snapshot.json": challenge,
        "a004_contract_gate_challenge_profiles.json": profiles,
        "a004_contract_gate_challenge_decisions.json": {
            "schema_version": "1.0", "rows": result["rows"]
        },
        "a004_contract_gate_challenge_report.json": result["report"],
    }
    for filename, value in artifacts.items():
        gate.write_json(output_dir / filename, value)
    manifest_rows = [
        {"filename": path.name, "sha256": gate.file_hash(path), "bytes": path.stat().st_size}
        for path in sorted(output_dir.iterdir(), key=lambda item: item.name)
    ]
    gate.write_json(output_dir / "artifact_manifest.json", {
        "schema_version": "1.0",
        "challenge_id": challenge["challenge_id"],
        "challenge_source_sha256": gate.file_hash(CHALLENGE_PATH),
        "artifact_count": len(manifest_rows),
        "artifacts": manifest_rows,
    })
    return result["report"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else gate.WORKSPACE / args.output_dir
    print(json.dumps(build_outputs(output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
