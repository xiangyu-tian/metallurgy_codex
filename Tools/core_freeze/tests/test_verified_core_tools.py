import math
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[2]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from models_core import ModelRegistry  # noqa: E402
from Tools.core_freeze.verified_core.validate_verified_core import (  # noqa: E402
    validate,
    validate_contract_shape,
)


class VerifiedCoreRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ModelRegistry()
        cls.registry.discover()

    def invoke(self, model_id, params):
        return self.registry.invoke(model_id, params)

    def test_a001_rejects_dimension_mismatch_at_tool_boundary(self):
        result = self.invoke(
            "A001",
            {"value": 1, "source_unit": "kg", "target_unit": "m"},
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "UNIT_MISMATCH")

    def test_a001_propagates_unknown_unit_failure(self):
        result = self.invoke(
            "A001",
            {"value": 1, "source_unit": "unknown", "target_unit": "m"},
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "INVALID_INPUT")

    def test_a001_exposes_affine_temperature_transform(self):
        result = self.invoke(
            "A001",
            {"value": 0, "source_unit": "°C", "target_unit": "K"},
        )
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.result["value"], 273.15)
        self.assertEqual(result.result["conversion_factor"], 1.0)
        self.assertEqual(result.result["conversion_offset"], 273.15)

    def test_a002_and_a003_reject_unconsumed_formula_suffix(self):
        for model_id in ("A002", "A003"):
            with self.subTest(model_id=model_id):
                result = self.invoke(model_id, {"formula": "Fe2O3abc"})
                self.assertFalse(result.success)
                self.assertEqual(result.error_code, "INVALID_INPUT")

    def test_a002_rejects_invalid_or_zero_stoichiometry(self):
        for formula in ("2Fe", "Fe0", "Fe2..3", "(OH)0", "()2"):
            with self.subTest(formula=formula):
                result = self.invoke("A002", {"formula": formula})
                self.assertFalse(result.success)
                self.assertEqual(result.error_code, "INVALID_INPUT")

    def test_a002_parses_nested_formula_without_losing_tokens(self):
        result = self.invoke("A002", {"formula": "[Cu(NH3)4]SO4"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(
            result.result["elements"],
            {"Cu": 1.0, "N": 4.0, "H": 12.0, "S": 1.0, "O": 4.0},
        )

    def test_a003_matches_independent_fe2o3_reference(self):
        result = self.invoke("A003", {"formula": "Fe2O3"})
        self.assertTrue(result.success, result.error)
        expected = 2 * 55.845 + 3 * 15.999
        self.assertTrue(
            math.isclose(
                result.result["molar_mass"],
                expected,
                rel_tol=0,
                abs_tol=1e-4,
            )
        )

    def test_a004_rejects_negative_nonfinite_and_invalid_tolerance(self):
        invalid_cases = [
            {"compositions": {"Fe": -0.1, "C": 1.1}},
            {"compositions": {"Fe": float("nan"), "C": 1.0}},
            {"compositions": {"Fe": float("inf"), "C": 1.0}},
            {"compositions": ["Fe", "C"]},
            {"compositions": {"Fe": "not-a-number", "C": 1.0}},
            {"compositions": {"Fe": True, "C": 1.0}},
            {"compositions": {"Fe": 1e308, "C": 1e308}},
            {"compositions": {"Fe": 0.9, "C": 0.1}, "tolerance": -0.1},
        ]
        for params in invalid_cases:
            with self.subTest(params=params):
                result = self.invoke("A004", params)
                self.assertFalse(result.success)
                self.assertEqual(result.error_code, "INVALID_INPUT")

    def test_a004_normalizes_nonnegative_weights(self):
        result = self.invoke(
            "A004",
            {"compositions": {"Fe": 94.0, "C": 4.0, "Si": 2.0}},
        )
        self.assertTrue(result.success, result.error)
        self.assertEqual(
            result.result["normalized"],
            {"Fe": 0.94, "C": 0.04, "Si": 0.02},
        )

    def test_b019_rejects_out_of_basis_or_nonfinite_compositions(self):
        invalid_cases = [
            {
                "overall_composition": -0.1,
                "phase1_composition": 0.0,
                "phase2_composition": 0.8,
                "composition_basis": "fraction",
            },
            {
                "overall_composition": 0.5,
                "phase1_composition": 0.2,
                "phase2_composition": 1.2,
                "composition_basis": "fraction",
            },
            {
                "overall_composition": float("nan"),
                "phase1_composition": 0.2,
                "phase2_composition": 0.8,
                "composition_basis": "fraction",
            },
            {
                "overall_composition": 50,
                "phase1_composition": 20,
                "phase2_composition": 120,
                "composition_basis": "percent",
            },
        ]
        for params in invalid_cases:
            with self.subTest(params=params):
                result = self.invoke("B019", params)
                self.assertFalse(result.success)
                self.assertEqual(result.error_code, "INVALID_INPUT")

    def test_b019_satisfies_fraction_and_conservation_invariants(self):
        result = self.invoke(
            "B019",
            {
                "overall_composition": 0.4,
                "phase1_composition": 0.2,
                "phase2_composition": 0.7,
                "composition_basis": "fraction",
            },
        )
        self.assertTrue(result.success, result.error)
        self.assertTrue(
            math.isclose(
                result.result["phase1_fraction"]
                + result.result["phase2_fraction"],
                1.0,
                rel_tol=0,
                abs_tol=1e-12,
            )
        )
        self.assertLessEqual(result.result["conservation_residual"], 1e-10)

    def test_b019_supports_explicit_percentage_scale(self):
        result = self.invoke(
            "B019",
            {
                "overall_composition": 40,
                "phase1_composition": 20,
                "phase2_composition": 70,
                "composition_basis": "percent",
            },
        )
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.result["phase1_fraction"], 0.6)
        self.assertEqual(result.result["phase2_fraction"], 0.4)
        self.assertEqual(result.result["composition_basis"], "percent")


class VerifiedCoreEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.verified_dir = TOOLS_DIR / "core_freeze" / "verified_core"

    def test_contracts_and_independent_reference_cases_pass(self):
        report = validate(
            self.verified_dir / "contracts_v1.json",
            self.verified_dir / "reference_cases_v1.json",
            None,
        )
        self.assertEqual(report["validation_status"], "passed")
        self.assertEqual(report["summary"]["contract_count"], 5)
        self.assertEqual(report["summary"]["case_count"], 27)
        self.assertEqual(report["summary"]["failed_case_count"], 0)

    def test_contract_hash_tampering_is_rejected(self):
        contracts = json.loads(
            (self.verified_dir / "contracts_v1.json").read_text(encoding="utf-8")
        )
        contract = copy.deepcopy(contracts["contracts"][0])
        contract["scientific_function"] = "tampered"
        errors = validate_contract_shape(contract)
        self.assertTrue(any("contract_hash mismatch" in error for error in errors))

    def test_artifact_manifest_uses_project_relative_source_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = validate(
                self.verified_dir / "contracts_v1.json",
                self.verified_dir / "reference_cases_v1.json",
                Path(temp_dir),
            )
            self.assertEqual(report["validation_status"], "passed")
            manifest = json.loads(
                (Path(temp_dir) / "artifact_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            filenames = [row["filename"] for row in manifest["artifacts"]]
            self.assertTrue(
                all(
                    not Path(filename).is_absolute() and ".." not in Path(filename).parts
                    for filename in filenames
                )
            )


if __name__ == "__main__":
    unittest.main()
