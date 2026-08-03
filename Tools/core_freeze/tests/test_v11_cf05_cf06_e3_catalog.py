import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.e3_routing import build_e3_schema_catalog as builder


class V11Cf05Cf06E3CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = builder.load_json(builder.CONFIG_PATH)
        cls.built = builder.build_catalog(cls.config)

    def test_catalog_separates_lifecycle_statuses(self):
        catalog = self.built["catalog"]
        self.assertEqual(catalog["entry_count"], 120)
        self.assertEqual(catalog["verified_executable_count"], 5)
        self.assertEqual(catalog["implemented_unverified_count"], 12)
        self.assertEqual(catalog["schema_only_planned_count"], 103)
        self.assertFalse(catalog["api_visible_lifecycle_labels"])

    def test_only_verified_core_can_be_formal_target_or_execute(self):
        allowed = {
            entry["tool_id"]
            for entry in self.built["catalog"]["entries"]
            if entry["formal_execution_allowed"] and entry["formal_target_allowed"]
        }
        self.assertEqual(allowed, {"A001", "A002", "A003", "A004", "B019"})

    def test_pools_are_exact_and_nested(self):
        pools = self.built["pools"]["pools"]
        self.assertEqual([pool["tool_count"] for pool in pools], [17, 50, 100, 120])
        for smaller, larger in zip(pools, pools[1:]):
            self.assertTrue(set(smaller["tool_ids"]).issubset(larger["tool_ids"]))
        self.assertEqual(len(set(pools[-1]["tool_ids"])), 120)

    def test_every_api_schema_is_structurally_valid(self):
        for entry in self.built["catalog"]["entries"]:
            builder.validate_openai_tool(entry["openai_tool"])
        planned = [
            entry for entry in self.built["catalog"]["entries"]
            if entry["lifecycle_status"] == "schema_only_planned"
        ]
        self.assertTrue(all("not_parameter_contract" in entry["schema_fidelity"] for entry in planned))

    def test_generated_package_is_offline_and_manifest_complete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            report = builder.build_outputs(output_dir)
            self.assertEqual(report["external_api_calls"], 0)
            self.assertFalse(report["external_api_calls_authorized"])
            self.assertEqual(report["status"], "candidate_generated_not_formally_eligible")
            manifest = json.loads((output_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifact_count"], 8)
            for artifact in manifest["artifacts"]:
                path = output_dir / artifact["filename"]
                self.assertTrue(path.is_file())
                self.assertEqual(builder.sha256_file(path), artifact["sha256"])


if __name__ == "__main__":
    unittest.main()
