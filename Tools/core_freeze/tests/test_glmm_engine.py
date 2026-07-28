"""Optional integration test for the frozen R/lme4 engine."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.formal_pipeline import FORMAL_OUTPUTS, run_formal_pipeline
from Tools.core_freeze.r_engine import (
    ENGINE_LOCK,
    REngineError,
    check_engine,
)
from Tools.core_freeze.tests.fixtures import formal_glmm_document


class GlmmEngineIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.versions = check_engine()
        except REngineError as error:
            raise unittest.SkipTest(str(error))
        cls.document = formal_glmm_document()

    def test_frozen_engine_versions(self):
        lock = json.loads(ENGINE_LOCK.read_text(encoding="utf-8"))
        expected = {"R": lock["r_version"], **lock["packages"]}
        self.assertEqual(self.versions, expected)

    def test_formal_pipeline_generates_complete_artifact_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = run_formal_pipeline(
                self.document,
                root,
                n_resamples=20,
                glmm_timeout=180,
            )

            self.assertEqual(report["formal_models"]["H3"]["status"], "converged")
            self.assertEqual(report["formal_models"]["H4"]["status"], "converged")
            self.assertEqual(report["cf11_status"], "in_progress")
            self.assertEqual(
                report["estimands"]["primary"]["effect"],
                "total_method_effect",
            )
            self.assertFalse(
                report["estimands"]["primary"][
                    "schema_token_count_adjusted"
                ]
            )
            self.assertEqual(
                report["cf11_components"]["synthetic_integration"],
                "passed",
            )
            self.assertEqual(
                report["cf11_components"]["real_candidate_dry_run"],
                "pending",
            )
            self.assertEqual(
                report["cf11_components"]["finalization_implementation"],
                "passed",
            )
            self.assertFalse(
                report["estimands"]["sensitivity"][
                    "allowed_to_change_primary_support_classification"
                ]
            )
            self.assertIsNone(
                report["estimands"]["sensitivity"][
                    "observed_conclusion_differs_from_primary"
                ]
            )
            self.assertEqual(len(report["r_engine_lock_hash"]), 64)
            self.assertIsNotNone(report["analysis_commit"])
            self.assertEqual(len(FORMAL_OUTPUTS), 30)
            self.assertTrue(
                all((root / filename).is_file() for filename in FORMAL_OUTPUTS)
            )
            with (root / "artifact_manifest.csv").open(
                encoding="utf-8-sig",
                newline="",
            ) as handle:
                manifest_rows = list(csv.DictReader(handle))
            self.assertEqual(len(manifest_rows), len(FORMAL_OUTPUTS) - 1)
            self.assertTrue(
                all(len(row["sha256"]) == 64 for row in manifest_rows)
            )
            with (root / "model_status.csv").open(
                encoding="utf-8-sig",
                newline="",
            ) as handle:
                status_rows = list(csv.DictReader(handle))
            self.assertEqual(len(status_rows), 5)
            self.assertEqual(
                {row["analysis_model"] for row in status_rows},
                {
                    "h3",
                    "h3_schema_adjusted_sensitivity",
                    "h3_method_interaction_sensitivity",
                    "h4",
                    "h4_schema_adjusted_sensitivity",
                },
            )
            with (root / "model_attempts.csv").open(
                encoding="utf-8-sig",
                newline="",
            ) as handle:
                attempts = list(csv.DictReader(handle))
            formulas = {
                row["analysis_model"]: row["formula"] for row in attempts
            }
            self.assertNotIn("schema_token_count_z", formulas["h3"])
            self.assertNotIn("schema_token_count_z", formulas["h4"])
            self.assertIn(
                "schema_token_count_z",
                formulas["h3_schema_adjusted_sensitivity"],
            )
            self.assertIn(
                "schema_token_count_z",
                formulas["h4_schema_adjusted_sensitivity"],
            )
            self.assertIn(
                "method * neighbor_condition",
                formulas["h3_method_interaction_sensitivity"],
            )
            with (
                root / "h3_method_interaction_sensitivity_contrasts.csv"
            ).open(encoding="utf-8-sig", newline="") as handle:
                interaction_rows = list(csv.DictReader(handle))
            self.assertEqual(
                {row["method"] for row in interaction_rows},
                {
                    "full_schema",
                    "lexical_top5",
                    "dense_top5",
                    "hierarchical",
                },
            )


if __name__ == "__main__":
    unittest.main()
