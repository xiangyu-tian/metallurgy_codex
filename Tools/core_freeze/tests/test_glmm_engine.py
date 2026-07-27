"""Optional integration test for the frozen R/lme4 engine."""

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
            self.assertTrue(
                all((root / filename).is_file() for filename in FORMAL_OUTPUTS)
            )


if __name__ == "__main__":
    unittest.main()
