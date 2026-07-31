import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.e2_contract_boundaries.analyze_e2_development import (
    build_analysis,
    file_hash,
    inspect_record,
    load_json,
    write_outputs,
)
from Tools.core_freeze.e2_contract_boundaries.run_e2_development import (
    OUTPUT_SCHEMA_PATH,
    POLICY_PATH,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SHARING_AUTHORIZATION_PATH = (
    PROJECT_ROOT
    / "Tools"
    / "core_freeze"
    / "e2_contract_boundaries"
    / "external_data_sharing_authorization_20260731.json"
)
SUCCESSFUL_RUN_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_model_development_r1_network_retry_20260731"
)


class V11Cf04E2DevelopmentAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.schema = load_json(OUTPUT_SCHEMA_PATH)
        self.policy = load_json(POLICY_PATH)

    def _record(self):
        return {
            "run_id": "TEST-RUN",
            "task_id": "TEST-001",
            "source_tool_id": "A001",
            "mutation_types": ["remove_required_parameter"],
            "expected_flags": ["missing_parameter"],
            "expected_primary_status": "missing_or_ambiguous_input",
            "expected_action": "clarify",
            "status": "completed",
            "schema_valid": False,
            "raw_output": json.dumps(
                {
                    "flags": ["missing_parameter"],
                    "primary_status": "missing_parameter",
                    "action": "clarify",
                }
            ),
        }

    def test_diagnostic_recovers_independent_fields_without_rescoring(self):
        row = inspect_record(
            self._record(),
            output_schema=self.schema,
            policy=self.policy,
        )
        self.assertFalse(row["strict_schema_valid"])
        self.assertTrue(row["flags_exact"])
        self.assertTrue(row["raw_action_correct"])
        self.assertFalse(row["primary_status_well_formed"])
        self.assertTrue(row["derived_primary_correct"])
        self.assertIn(
            "primary_status_mapping_error",
            row["error_types"],
        )

    def test_analysis_preserves_strict_summary(self):
        strict_summary = {"schema_valid_rate": 0.0}
        report = {
            "run_id": "TEST-RUN",
            "run_config_id": "TEST-CONFIG",
            "dataset_id": "TEST-DATASET",
            "summary": strict_summary,
            "model_policy_revision_allowed": False,
        }
        diagnostics, mutations, analysis = build_analysis(
            [self._record()],
            run_report=report,
            output_schema=self.schema,
            policy=self.policy,
        )
        self.assertEqual(analysis["strict_summary"], strict_summary)
        self.assertTrue(analysis["strict_score_unchanged"])
        self.assertEqual(
            analysis["parsed_field_diagnostic"]["flags_exact_accuracy"],
            1.0,
        )
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(len(mutations), 1)

    def test_output_manifest_binds_source_and_contains_no_secret(self):
        report = {
            "run_id": "TEST-RUN",
            "run_config_id": "TEST-CONFIG",
            "dataset_id": "TEST-DATASET",
            "summary": {"schema_valid_rate": 0.0},
            "model_policy_revision_allowed": False,
        }
        diagnostics, mutations, analysis = build_analysis(
            [self._record()],
            run_report=report,
            output_schema=self.schema,
            policy=self.policy,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            source.mkdir()
            for filename in (
                "run_records.jsonl",
                "run_report.json",
                "artifact_manifest.json",
            ):
                (source / filename).write_text(
                    "{}\n",
                    encoding="utf-8",
                )
            output = root / "analysis"
            write_outputs(
                output_dir=output,
                source_dir=source,
                diagnostics=diagnostics,
                mutation_summary=mutations,
                analysis=analysis,
            )
            manifest = json.loads(
                (output / "artifact_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            for artifact in manifest["artifacts"]:
                self.assertEqual(
                    file_hash(output / artifact["filename"]),
                    artifact["sha256"],
                )
            combined = "\n".join(
                path.read_text(encoding="utf-8")
                for path in output.iterdir()
            )
            self.assertNotIn("sk-", combined)
            self.assertTrue(manifest["strict_score_unchanged"])

    def test_external_sharing_authorization_binds_successful_run(self):
        authorization = load_json(SHARING_AUTHORIZATION_PATH)
        run_report = load_json(SUCCESSFUL_RUN_DIR / "run_report.json")
        self.assertTrue(authorization["received_before_execution"])
        self.assertEqual(authorization["scope"]["task_count"], 55)
        self.assertEqual(
            authorization["successful_run_id"],
            run_report["run_id"],
        )
        self.assertEqual(
            authorization["successful_run_manifest_sha256"],
            file_hash(SUCCESSFUL_RUN_DIR / "artifact_manifest.json"),
        )
        self.assertEqual(
            authorization["scope"]["tool_access"],
            "disabled",
        )


if __name__ == "__main__":
    unittest.main()
