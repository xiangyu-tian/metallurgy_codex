"""Audit v1.1 Core Freeze gates CF-01 and CF-02."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
PROTOCOL_PATH = (
    PROJECT_ROOT / "docs" / "experiments" / "research_protocol_v1.1-rc1.md"
)
DATA_POLICY_PATH = (
    PROJECT_ROOT
    / "docs"
    / "experiments"
    / "dataset_executable_reference_policy_v1.0-rc1.md"
)
RATIONALE_PATH = (
    PROJECT_ROOT
    / "docs"
    / "experiments"
    / "research_protocol_revision_rationale_20260730.md"
)
VERIFIED_DIR = HERE / "verified_core"
CONTRACT_SCHEMA_PATH = VERIFIED_DIR / "tool_contract.schema.json"
CONTRACTS_PATH = VERIFIED_DIR / "contracts_v1.json"
REFERENCE_CASES_PATH = VERIFIED_DIR / "reference_cases_v1.json"
VALIDATOR_PATH = VERIFIED_DIR / "validate_verified_core.py"
PUBLISHED_DIR = (
    PROJECT_ROOT / "outputs" / "verified_core_v1_20260730"
)
PUBLISHED_REPORT_PATH = PUBLISHED_DIR / "validation_report.json"
PUBLISHED_MANIFEST_PATH = PUBLISHED_DIR / "artifact_manifest.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def check(check_id: str, passed: bool, evidence: str) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "passed": bool(passed),
        "evidence": evidence,
    }


def verify_published_manifest(
    manifest: dict[str, Any],
) -> tuple[bool, list[str]]:
    errors = []
    for row in manifest.get("artifacts", []):
        name = row.get("filename")
        if not isinstance(name, str):
            errors.append("manifest filename is not a string")
            continue
        candidate = Path(name)
        if candidate.is_absolute() or ".." in candidate.parts:
            errors.append(f"unsafe manifest path: {name}")
            continue
        if candidate.parts and candidate.parts[0] in {
            "Tools",
            "docs",
            "outputs",
        }:
            artifact = PROJECT_ROOT / candidate
        else:
            artifact = PUBLISHED_DIR / candidate
        if not artifact.is_file():
            errors.append(f"missing manifest artifact: {name}")
        elif file_hash(artifact) != row.get("sha256"):
            errors.append(f"manifest hash mismatch: {name}")
    return not errors, errors


def audit_cf01() -> dict[str, Any]:
    protocol = PROTOCOL_PATH.read_text(encoding="utf-8")
    policy = DATA_POLICY_PATH.read_text(encoding="utf-8")
    rationale = RATIONALE_PATH.read_text(encoding="utf-8")
    checks = [
        check(
            "CF01-PROTOCOL-VERSION",
            "版本：`1.1-rc1`" in protocol,
            "research_protocol_v1.1-rc1.md declares version 1.1-rc1",
        ),
        check(
            "CF01-DATA-POLICY-VERSION",
            "版本：`1.0-rc1`" in policy
            and "research_protocol_v1.1-rc1.md" in policy,
            "dataset policy identifies its version and companion protocol",
        ),
        check(
            "CF01-EXPERT-FREE-CRITICAL-PATH",
            "将专家逐题标注从正式确认性实验的关键路径中移除"
            in rationale,
            "revision rationale explicitly removes per-item expert labels",
        ),
        check(
            "CF01-TRUTH-TIERS",
            all(token in rationale for token in ("| G1 |", "| G2 |", "| C1 |", "| S1 |")),
            "revision rationale defines G1/G2/C1/S1 truth tiers",
        ),
        check(
            "CF01-CONFIRMATORY-TRUTH-SCOPE",
            "正式确认性结论只允许使用G1、G2和C1" in rationale,
            "formal conclusions are limited to externally or executably verified truth",
        ),
        check(
            "CF01-SILVER-NOT-GOLD",
            "AI辅助标签只能作为`provisional_silver`" in rationale,
            "AI-assisted labels remain provisional silver",
        ),
        check(
            "CF01-DATA-PRODUCTION-PIPELINE",
            all(
                token in policy
                for token in (
                    "先注册和验证工具",
                    "独立参考实现",
                    "AI生成文本只负责表述扩展",
                    "运行结果没有回写基础真值",
                )
            ),
            "data policy fixes contract-first, independent-reference production",
        ),
        check(
            "CF01-NOT-FROZEN",
            "core_frozen = false" in protocol
            and "core_frozen = false" in policy,
            "both candidate documents preserve Core Frozen=false",
        ),
    ]
    return {
        "check_id": "CF-01",
        "title": "v1.1协议与可执行数据规范兼容性",
        "status": "passed" if all(row["passed"] for row in checks) else "failed",
        "checks": checks,
        "source_hashes": {
            relative(PROTOCOL_PATH): file_hash(PROTOCOL_PATH),
            relative(DATA_POLICY_PATH): file_hash(DATA_POLICY_PATH),
            relative(RATIONALE_PATH): file_hash(RATIONALE_PATH),
        },
        "acceptance_scope": (
            "Compatibility and truth-governance only; this does not validate "
            "all later experiments or make Core Frozen true."
        ),
    }


def audit_cf02() -> dict[str, Any]:
    from Tools.core_freeze.verified_core.validate_verified_core import (
        validate,
        validate_contract_shape,
    )

    contracts_doc = load_json(CONTRACTS_PATH)
    contracts = contracts_doc.get("contracts", [])
    published = load_json(PUBLISHED_REPORT_PATH)
    manifest = load_json(PUBLISHED_MANIFEST_PATH)
    runtime = validate(CONTRACTS_PATH, REFERENCE_CASES_PATH, None)
    manifest_passed, manifest_errors = verify_published_manifest(manifest)
    shape_errors = {
        row.get("tool_id", f"index-{index}"): validate_contract_shape(row)
        for index, row in enumerate(contracts)
    }
    all_shape_valid = all(not errors for errors in shape_errors.values())
    tool_ids = [row.get("tool_id") for row in contracts]
    checks = [
        check(
            "CF02-MINIMUM-TOOL-COUNT",
            len(contracts) >= 3,
            f"verified contract count={len(contracts)}, required>=3",
        ),
        check(
            "CF02-UNIQUE-TOOLS",
            len(tool_ids) == len(set(tool_ids)) and None not in tool_ids,
            f"tool ids={tool_ids}",
        ),
        check(
            "CF02-VERIFIED-STATUS",
            all(row.get("tool_status") == "verified_core" for row in contracts),
            "all accepted contracts declare verified_core",
        ),
        check(
            "CF02-CONTRACT-SHAPE-HASH",
            all_shape_valid,
            json.dumps(shape_errors, ensure_ascii=False, sort_keys=True),
        ),
        check(
            "CF02-SOURCES-AND-SCOPE",
            all(
                row.get("reference_sources")
                and row.get("verification_scope")
                and row.get("known_limitations") is not None
                for row in contracts
            ),
            "each contract has references, verification scope and limitations",
        ),
        check(
            "CF02-RUNTIME-REVALIDATION",
            runtime.get("validation_status") == "passed"
            and runtime.get("summary", {}).get("contract_count") >= 3
            and runtime.get("summary", {}).get("failed_case_count") == 0,
            json.dumps(runtime.get("summary"), ensure_ascii=False),
        ),
        check(
            "CF02-NORMAL-BOUNDARY-COVERAGE",
            all(
                row.get("status") == "passed"
                and not row.get("missing_required_case_types")
                for row in runtime.get("coverage_results", [])
            ),
            "all five tools contain required normal and boundary coverage",
        ),
        check(
            "CF02-PUBLISHED-EVIDENCE",
            published.get("validation_status") == "passed"
            and published.get("summary", {}).get("contract_count") == len(contracts)
            and published.get("summary", {}).get("failed_case_count") == 0,
            json.dumps(published.get("summary"), ensure_ascii=False),
        ),
        check(
            "CF02-PUBLISHED-MANIFEST",
            manifest_passed,
            (
                "published manifest hashes verified"
                if manifest_passed
                else json.dumps(manifest_errors, ensure_ascii=False)
            ),
        ),
        check(
            "CF02-INDEPENDENT-REFERENCE",
            bool(runtime.get("independent_oracle"))
            and "not computed by production tool implementations"
            in runtime.get("independent_oracle", ""),
            runtime.get("independent_oracle", ""),
        ),
        check(
            "CF02-NOT-FROZEN",
            runtime.get("core_frozen") is False,
            "verified core acceptance does not set Core Frozen=true",
        ),
    ]
    return {
        "check_id": "CF-02",
        "title": "至少3个verified_core工具及独立参考验证",
        "status": "passed" if all(row["passed"] for row in checks) else "failed",
        "checks": checks,
        "verified_tool_ids": tool_ids,
        "verified_tool_count": len(tool_ids),
        "reference_case_count": runtime.get("summary", {}).get("case_count"),
        "passed_reference_case_count": runtime.get("summary", {}).get(
            "passed_case_count"
        ),
        "source_hashes": {
            relative(CONTRACT_SCHEMA_PATH): file_hash(CONTRACT_SCHEMA_PATH),
            relative(CONTRACTS_PATH): file_hash(CONTRACTS_PATH),
            relative(REFERENCE_CASES_PATH): file_hash(REFERENCE_CASES_PATH),
            relative(VALIDATOR_PATH): file_hash(VALIDATOR_PATH),
            relative(PUBLISHED_REPORT_PATH): file_hash(PUBLISHED_REPORT_PATH),
            relative(PUBLISHED_MANIFEST_PATH): file_hash(
                PUBLISHED_MANIFEST_PATH
            ),
        },
        "acceptance_scope": (
            "Only the five contract verification scopes are accepted. This "
            "does not validate the remaining 12 implemented or 103 planned tools."
        ),
    }


def run_audit(output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    cf01 = audit_cf01()
    cf02 = audit_cf02()
    passed = cf01["status"] == "passed" and cf02["status"] == "passed"
    report = {
        "schema_version": "1.0",
        "audit_id": "V11-CF01-CF02-AUDIT-20260731",
        "protocol_version": "1.1-rc1",
        "status": "passed" if passed else "failed",
        "checks": {"cf01": cf01, "cf02": cf02},
        "legacy_cf01_cf02_reused_as_formal_gold": False,
        "provisional_silver_promoted": False,
        "core_frozen": False,
    }
    output_dir.mkdir(parents=True)
    report_path = output_dir / "audit_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    source_paths = [
        PROTOCOL_PATH,
        DATA_POLICY_PATH,
        RATIONALE_PATH,
        CONTRACT_SCHEMA_PATH,
        CONTRACTS_PATH,
        REFERENCE_CASES_PATH,
        VALIDATOR_PATH,
        PUBLISHED_REPORT_PATH,
        PUBLISHED_MANIFEST_PATH,
        Path(__file__),
    ]
    manifest = {
        "schema_version": "1.0",
        "audit_id": report["audit_id"],
        "artifacts": [
            {
                "filename": report_path.name,
                "sha256": file_hash(report_path),
            }
        ],
        "source_artifacts": [
            {"filename": relative(path), "sha256": file_hash(path)}
            for path in source_paths
        ],
        "core_frozen": False,
    }
    manifest_path = output_dir / "artifact_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=(
            PROJECT_ROOT / "outputs" / "v11_cf01_cf02_audit_20260731"
        ),
    )
    args = parser.parse_args()
    report = run_audit(args.output_dir)
    print(
        json.dumps(
            {
                "audit_id": report["audit_id"],
                "status": report["status"],
                "cf01": report["checks"]["cf01"]["status"],
                "cf02": report["checks"]["cf02"]["status"],
                "core_frozen": report["core_frozen"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
