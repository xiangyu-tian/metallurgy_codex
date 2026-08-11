import hashlib
import json
import math
import sys
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[2]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from models_core import ModelRegistry  # noqa: E402
from Tools.core_freeze.e3_routing import a004_contract_adjudication as common  # noqa: E402
from Tools.core_freeze.e3_routing import validate_b019_runtime_remediation as validation  # noqa: E402


class V11Cf05E3B019RuntimeRemediationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ModelRegistry()
        cls.registry.discover()

    def invoke(self, **overrides):
        params = {
            "overall_composition": 0.4,
            "phase1_composition": 0.2,
            "phase2_composition": 0.7,
            "composition_basis": "fraction",
            **overrides,
        }
        return self.registry.invoke("B019", params)

    def test_component_schema_has_no_implicit_default(self):
        model = self.registry.get("B019")
        component = next(field.to_dict() for field in model.input_fields if field.name == "component")
        self.assertNotIn("default", component)
        self.assertFalse(component["required"])

    def test_omitted_component_remains_unspecified(self):
        result = self.invoke()
        self.assertTrue(result.success, result.error)
        self.assertIsNone(result.result["component"])
        self.assertEqual(result.result["component_grounding_status"], "unspecified")

    def test_explicit_component_is_preserved_and_marked_explicit(self):
        result = self.invoke(component="Fe")
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.result["component"], "Fe")
        self.assertEqual(result.result["component_grounding_status"], "explicit")

    def test_component_remediation_does_not_change_lever_rule_result(self):
        omitted = self.invoke()
        explicit = self.invoke(component="Fe")
        self.assertTrue(omitted.success and explicit.success)
        for field in ("phase1_fraction", "phase2_fraction", "conservation_residual"):
            self.assertTrue(math.isclose(omitted.result[field], explicit.result[field], abs_tol=1e-12))

    def test_legacy_auto_basis_remains_available_only_for_compatibility(self):
        model = self.registry.get("B019")
        basis = next(field.to_dict() for field in model.input_fields if field.name == "composition_basis")
        self.assertEqual(basis["default"], "auto")
        self.assertIn("auto", basis["enum"])

    def test_frozen_replay_passes_without_implicit_component(self):
        result = validation.validate(common.load_json(validation.CONFIG_PATH))
        report = result["report"]
        self.assertEqual(report["validation_status"], "passed")
        self.assertEqual(report["replay_passed_count"], 16)
        self.assertEqual(report["implicit_component_output_count"], 0)
        self.assertEqual(report["unspecified_component_output_count"], 16)
        self.assertEqual(report["external_api_calls"], 0)

    def test_runtime_remediation_manifest_matches_outputs(self):
        output_dir = common.WORKSPACE / "outputs/v11_cf05_e3_b019_runtime_remediation_v1_20260811"
        manifest = json.loads((output_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["artifact_count"], 4)
        for row in manifest["artifacts"]:
            path = output_dir / row["filename"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])


if __name__ == "__main__":
    unittest.main()
