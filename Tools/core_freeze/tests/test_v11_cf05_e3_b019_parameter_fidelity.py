import hashlib
import json
import unittest

from Tools.core_freeze.e3_routing import a004_contract_adjudication as common
from Tools.core_freeze.e3_routing import audit_e3_b019_parameter_fidelity as audit


class V11Cf05E3B019ParameterFidelityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = audit.audit(common.load_json(audit.CONFIG_PATH))

    def test_legacy_scoring_overstates_parameter_fidelity(self):
        report = self.result["report"]
        self.assertEqual(report["cell_count"], 16)
        self.assertEqual(report["legacy_parameters_correct_count"], 16)
        self.assertEqual(report["strict_parameter_evidence_fidelity_count"], 5)
        self.assertEqual(report["legacy_parameter_false_positive_count"], 11)
        self.assertEqual(report["ungrounded_component_values"], {"B": 11})

    def test_audit_does_not_claim_scientific_results_are_wrong(self):
        self.assertFalse(self.result["report"]["scientific_result_error_inferred"])
        self.assertTrue(all(not row["scientific_result_incorrect_claimed"] for row in self.result["rows"]))

    def test_formal_schema_matches_verified_contract_boundary(self):
        candidate = self.result["formal_schema_candidate"]
        params = candidate["openai_tool"]["function"]["parameters"]
        self.assertEqual(params["required"], [
            "overall_composition", "phase1_composition", "phase2_composition", "composition_basis"
        ])
        self.assertEqual(params["properties"]["composition_basis"]["enum"], ["fraction", "percent"])
        self.assertNotIn("default", params["properties"]["composition_basis"])
        self.assertNotIn("default", params["properties"]["component"])
        self.assertFalse(params["additionalProperties"])
        self.assertFalse(candidate["formal_catalog_mutated"])

    def test_policy_escalation_is_rejected(self):
        config = common.load_json(audit.CONFIG_PATH)
        config["formal_catalog_mutation_allowed"] = True
        with self.assertRaisesRegex(ValueError, "must remain false"):
            audit.audit(config)

    def test_manifest_matches_outputs(self):
        output_dir = common.WORKSPACE / "outputs/v11_cf05_e3_b019_parameter_fidelity_audit_v1_20260811"
        manifest = json.loads((output_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["artifact_count"], 6)
        for row in manifest["artifacts"]:
            path = output_dir / row["filename"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])


if __name__ == "__main__":
    unittest.main()
