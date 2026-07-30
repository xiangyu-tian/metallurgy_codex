"""Validate verified-core contracts against frozen independent reference cases."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parents[1]
PROJECT_ROOT = HERE.parents[2]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from models_core import ModelRegistry  # noqa: E402


REQUIRED_CONTRACT_FIELDS = {
    "contract_id",
    "tool_id",
    "tool_version",
    "tool_status",
    "scientific_family",
    "scientific_function",
    "required_inputs",
    "optional_inputs",
    "output_contract",
    "validation_rules",
    "reference_sources",
    "verification_scope",
    "known_limitations",
    "contract_version",
    "contract_hash",
}
ALLOWED_STATUSES = {
    "verified_core",
    "conditionally_verified",
    "unverified",
    "known_defect",
}
REQUIRED_CASE_TYPES = {"normal", "boundary"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_contract_hash(contract: dict[str, Any]) -> str:
    payload = copy.deepcopy(contract)
    payload.pop("contract_hash", None)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_relative_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError(
            f"evidence source must be inside project root: {resolved}"
        ) from exc


def resolve_path(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(path)
        value = value[part]
    return value


def run_check(actual: Any, check: dict[str, Any]) -> tuple[bool, str]:
    op = check["op"]
    expected = check["value"]
    if op == "equal":
        passed = actual == expected
    elif op == "approx":
        passed = math.isclose(
            float(actual),
            float(expected),
            rel_tol=float(check.get("rel_tol", 0.0)),
            abs_tol=float(check.get("abs_tol", 0.0)),
        )
    elif op == "less_equal":
        passed = float(actual) <= float(expected)
    else:
        return False, f"unsupported comparison operator: {op}"
    return passed, f"actual={actual!r}, expected={expected!r}, op={op}"


def validate_contract_shape(contract: dict[str, Any]) -> list[str]:
    errors = []
    missing = sorted(REQUIRED_CONTRACT_FIELDS - contract.keys())
    if missing:
        errors.append(f"missing fields: {missing}")
    if contract.get("tool_status") not in ALLOWED_STATUSES:
        errors.append(f"invalid tool_status: {contract.get('tool_status')!r}")
    if not contract.get("required_inputs"):
        errors.append("required_inputs must not be empty")
    if not contract.get("validation_rules"):
        errors.append("validation_rules must not be empty")
    if not contract.get("reference_sources"):
        errors.append("reference_sources must not be empty")
    expected_hash = canonical_contract_hash(contract)
    if contract.get("contract_hash") != expected_hash:
        errors.append(
            "contract_hash mismatch: "
            f"stored={contract.get('contract_hash')!r}, expected={expected_hash}"
        )
    return errors


def validate_case(registry: ModelRegistry, case: dict[str, Any]) -> dict[str, Any]:
    result = registry.invoke(case["tool_id"], case["input"])
    expected = case["expected"]
    failures = []
    if result.success != expected["success"]:
        failures.append(
            f"success mismatch: actual={result.success}, "
            f"expected={expected['success']}"
        )
    if not expected["success"]:
        expected_code = expected.get("error_code")
        if expected_code and result.error_code != expected_code:
            failures.append(
                f"error_code mismatch: actual={result.error_code!r}, "
                f"expected={expected_code!r}"
            )
    elif result.result is None:
        failures.append("successful result has no payload")
    else:
        for check in expected.get("checks", []):
            try:
                actual = resolve_path(result.result, check["path"])
            except KeyError:
                failures.append(f"missing result path: {check['path']}")
                continue
            passed, detail = run_check(actual, check)
            if not passed:
                failures.append(f"{check['path']}: {detail}")

    return {
        "case_id": case["case_id"],
        "tool_id": case["tool_id"],
        "case_type": case["case_type"],
        "status": "passed" if not failures else "failed",
        "failures": failures,
        "runtime_ms": result.runtime_ms,
    }


def validate(
    contracts_path: Path,
    cases_path: Path,
    output_dir: Path | None,
) -> dict[str, Any]:
    contracts_doc = load_json(contracts_path)
    cases_doc = load_json(cases_path)
    contracts = contracts_doc.get("contracts", [])
    cases = cases_doc.get("cases", [])

    registry = ModelRegistry()
    registry.discover()

    contract_ids = [item.get("contract_id") for item in contracts]
    tool_ids = [item.get("tool_id") for item in contracts]
    case_ids = [item.get("case_id") for item in cases]
    global_errors = []
    if len(contract_ids) != len(set(contract_ids)):
        global_errors.append("duplicate contract_id")
    if len(tool_ids) != len(set(tool_ids)):
        global_errors.append("duplicate tool_id contract")
    if len(case_ids) != len(set(case_ids)):
        global_errors.append("duplicate case_id")

    contract_results = []
    for contract in contracts:
        errors = validate_contract_shape(contract)
        model = registry.get(contract.get("tool_id", ""))
        if model is None:
            errors.append("tool is not discoverable")
        elif model.version != contract.get("tool_version"):
            errors.append(
                f"tool version mismatch: runtime={model.version}, "
                f"contract={contract.get('tool_version')}"
            )
        contract_results.append(
            {
                "contract_id": contract.get("contract_id"),
                "tool_id": contract.get("tool_id"),
                "status": "passed" if not errors else "failed",
                "errors": errors,
                "computed_contract_hash": canonical_contract_hash(contract),
            }
        )

    case_results = [validate_case(registry, case) for case in cases]
    cases_by_tool: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        cases_by_tool[case["tool_id"]].append(case)

    coverage_results = []
    for tool_id in tool_ids:
        types = {case["case_type"] for case in cases_by_tool[tool_id]}
        missing_types = sorted(REQUIRED_CASE_TYPES - types)
        coverage_results.append(
            {
                "tool_id": tool_id,
                "case_count": len(cases_by_tool[tool_id]),
                "case_type_counts": dict(
                    sorted(
                        Counter(
                            case["case_type"] for case in cases_by_tool[tool_id]
                        ).items()
                    )
                ),
                "status": "passed" if not missing_types else "failed",
                "missing_required_case_types": missing_types,
            }
        )

    passed = (
        not global_errors
        and contracts
        and cases
        and all(row["status"] == "passed" for row in contract_results)
        and all(row["status"] == "passed" for row in case_results)
        and all(row["status"] == "passed" for row in coverage_results)
    )
    report = {
        "schema_version": "1.0",
        "validation_id": "VERIFIED-CORE-V1-20260730",
        "validation_status": "passed" if passed else "failed",
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "independent_oracle": cases_doc.get("independence_statement"),
        "global_errors": global_errors,
        "summary": {
            "contract_count": len(contracts),
            "case_count": len(cases),
            "passed_case_count": sum(
                row["status"] == "passed" for row in case_results
            ),
            "failed_case_count": sum(
                row["status"] == "failed" for row in case_results
            ),
        },
        "contract_results": contract_results,
        "coverage_results": coverage_results,
        "case_results": case_results,
        "evidence_hashes": {
            "contracts_source_sha256": file_hash(contracts_path),
            "reference_cases_sha256": file_hash(cases_path),
        },
        "known_limitations": [
            "通过仅适用于各合同 verification_scope 明确列出的范围",
            "本验证不证明相图端点、真实材料状态或开放域问题描述正确",
            "确认性任务生成器仍须强制执行合同范围和版本",
        ],
        "core_frozen": False,
    }

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "validation_report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest = {
            "schema_version": "1.0",
            "validation_id": report["validation_id"],
            "artifacts": [
                {
                    "filename": report_path.name,
                    "sha256": file_hash(report_path),
                },
                {
                    "filename": project_relative_path(contracts_path),
                    "sha256": file_hash(contracts_path),
                },
                {
                    "filename": project_relative_path(cases_path),
                    "sha256": file_hash(cases_path),
                },
            ],
        }
        (output_dir / "artifact_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contracts",
        type=Path,
        default=HERE / "contracts_v1.json",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=HERE / "reference_cases_v1.json",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--print-contract-hashes", action="store_true")
    args = parser.parse_args()

    if args.print_contract_hashes:
        contracts = load_json(args.contracts).get("contracts", [])
        for contract in contracts:
            print(
                f"{contract['contract_id']} "
                f"{canonical_contract_hash(contract)}"
            )
        return 0

    report = validate(args.contracts, args.cases, args.output_dir)
    print(json.dumps(report["summary"], ensure_ascii=False))
    if report["global_errors"]:
        print(json.dumps(report["global_errors"], ensure_ascii=False))
    return 0 if report["validation_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
