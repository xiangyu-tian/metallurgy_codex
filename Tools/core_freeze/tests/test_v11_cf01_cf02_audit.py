import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.audit_v11_cf01_cf02 import (
    PROJECT_ROOT,
    audit_cf01,
    audit_cf02,
    file_hash,
    run_audit,
)


class V11Cf01Cf02AuditTests(unittest.TestCase):
    def test_cf01_protocol_and_data_policy_are_compatible(self):
        result = audit_cf01()
        self.assertEqual(result["status"], "passed")
        self.assertTrue(all(row["passed"] for row in result["checks"]))

    def test_cf02_has_five_independently_verified_tools(self):
        result = audit_cf02()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["verified_tool_count"], 5)
        self.assertEqual(result["reference_case_count"], 27)
        self.assertEqual(result["passed_reference_case_count"], 27)
        self.assertTrue(all(row["passed"] for row in result["checks"]))

    def test_audit_output_preserves_silver_and_core_freeze_boundaries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "audit"
            report = run_audit(output_dir)
            self.assertEqual(report["status"], "passed")
            self.assertFalse(report["legacy_cf01_cf02_reused_as_formal_gold"])
            self.assertFalse(report["provisional_silver_promoted"])
            self.assertFalse(report["core_frozen"])

            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            for row in manifest["artifacts"]:
                artifact = output_dir / row["filename"]
                self.assertTrue(artifact.is_file())
                self.assertEqual(file_hash(artifact), row["sha256"])
            for row in manifest["source_artifacts"]:
                source = PROJECT_ROOT / row["filename"]
                self.assertTrue(source.is_file())
                self.assertEqual(file_hash(source), row["sha256"])

    def test_audit_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "audit"
            run_audit(output_dir)
            with self.assertRaises(FileExistsError):
                run_audit(output_dir)


if __name__ == "__main__":
    unittest.main()
