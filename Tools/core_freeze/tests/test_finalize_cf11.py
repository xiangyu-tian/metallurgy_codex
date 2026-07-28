"""Tests for the separate CF-11 review and approval stage."""

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.finalize_cf11 import (
    FinalizationError,
    finalize_cf11,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FinalizeCf11Tests(unittest.TestCase):
    def build_fixture(self, root: Path):
        analysis = root / "analysis"
        evidence = root / "evidence"
        analysis.mkdir()
        evidence.mkdir()
        data_path = analysis / "data.csv"
        data_path.write_text("value\n1\n", encoding="utf-8")
        report_path = analysis / "confirmatory_report.json"
        report = {
            "artifact_files": [
                "data.csv",
                "confirmatory_report.json",
                "artifact_manifest.csv",
            ],
            "input_hash": "a" * 64,
            "r_engine_lock_hash": "b" * 64,
            "analysis_commit": "c" * 40,
            "tracked_worktree_clean": True,
            "cf11_status": "in_progress",
            "cf11_components": {
                "design_specification": "passed",
                "estimand_definition": "passed",
                "sensitivity_specification": "passed",
                "engine_implementation": "passed",
                "synthetic_integration": "passed",
                "artifact_contract": "passed",
            },
            "model_statuses": {
                "h3": "converged",
                "h3_schema_adjusted_sensitivity": "converged",
                "h3_method_interaction_sensitivity": "failed",
                "h4": "converged",
                "h4_schema_adjusted_sensitivity": "converged",
            },
        }
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest_path = analysis / "artifact_manifest.csv"
        with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=("filename", "sha256"),
            )
            writer.writeheader()
            for path in (data_path, report_path):
                writer.writerow({"filename": path.name, "sha256": sha256(path)})
        manifest_hash = sha256(manifest_path)

        common = {
            "input_hash": report["input_hash"],
            "analysis_commit": report["analysis_commit"],
            "artifact_manifest_hash": manifest_hash,
            "reviewer": "reviewer",
            "signed_at": "2026-07-28T12:00:00+08:00",
        }
        records = {
            "candidate_evidence": {
                **common,
                "record_type": "real_candidate_dry_run",
                "status": "passed",
            },
            "statistics_review": {
                **common,
                "record_type": "statistical_review",
                "decision": "approved",
            },
            "report_review": {
                **common,
                "record_type": "report_review",
                "decision": "approved",
            },
            "approval": {
                **common,
                "record_type": "project_approval",
                "decision": "approved",
            },
        }
        paths = {}
        for name, record in records.items():
            path = evidence / f"{name}.json"
            path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            paths[name] = path
        return analysis, paths, data_path

    def test_finalization_requires_bound_signed_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            analysis, evidence, _ = self.build_fixture(root)
            output = root / "cf11_finalization_record.json"
            record = finalize_cf11(
                analysis,
                **evidence,
                output=output,
            )
            self.assertEqual(record["cf11_status"], "passed")
            self.assertFalse(record["core_frozen"])
            self.assertEqual(
                record["cf11_components"]["real_candidate_dry_run"],
                "passed",
            )
            self.assertTrue(output.is_file())

    def test_finalization_rejects_tampered_analysis_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            analysis, evidence, data_path = self.build_fixture(root)
            data_path.write_text("value\n2\n", encoding="utf-8")
            with self.assertRaisesRegex(
                FinalizationError,
                "artifact hash mismatch",
            ):
                finalize_cf11(
                    analysis,
                    **evidence,
                    output=root / "record.json",
                )


if __name__ == "__main__":
    unittest.main()
