import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.e3_routing import build_e3_expansion_plan as builder


class V11Cf05E3ExpansionPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = builder.load_json(builder.CONFIG_PATH)
        cls.result = builder.build_plan(cls.config)

    def test_target_gaps_come_from_corrected_audit(self):
        rows = {
            row["target_tool_id"]: row
            for row in self.result["requirement_matrix"]["requirements"]
        }
        self.assertEqual(rows["A001"]["lexical_gap_to_8"], 8)
        self.assertEqual(rows["A002"]["lexical_gap_to_8"], 7)
        self.assertEqual(rows["A003"]["lexical_gap_to_8"], 4)
        self.assertEqual(rows["A004"]["lexical_gap_to_8"], 7)
        self.assertEqual(rows["B019"]["lexical_gap_to_8"], 4)
        self.assertTrue(
            all(row["contract_mismatch_gap_to_8"] == 8 for row in rows.values())
        )

    def test_capacity_floor_and_conservative_ceiling_are_separate(self):
        matrix = self.result["requirement_matrix"]
        self.assertEqual(matrix["lexical_gap_total"], 30)
        self.assertEqual(matrix["contract_mismatch_gap_total"], 40)
        self.assertEqual(matrix["conservative_distinct_slot_count"], 70)
        self.assertEqual(matrix["minimum_capacity_catalog_size"], 136)
        self.assertEqual(matrix["conservative_no_reuse_catalog_size"], 190)
        self.assertIsNone(matrix["actual_unique_expansion_count"])

    def test_slots_are_unfilled_and_do_not_invent_tools(self):
        template = self.result["slot_template"]
        self.assertEqual(template["slot_count"], 70)
        self.assertTrue(template["all_slots_unfilled"])
        self.assertFalse(template["invented_tool_identity_allowed"])
        self.assertEqual(len({row["slot_id"] for row in template["slots"]}), 70)
        self.assertTrue(all(row["candidate_tool_id"] is None for row in template["slots"]))

    def test_entry_schema_requires_structured_applicability_and_evidence(self):
        schema = self.result["entry_schema"]
        required = set(schema["required"])
        self.assertIn("applicability_contract", required)
        self.assertIn("source_provenance", required)
        self.assertIn("neighbor_relations", required)
        applicability = schema["properties"]["applicability_contract"]
        self.assertTrue(
            {"phases", "temperature_range", "pressure_range", "systems", "version", "availability"}
            .issubset(set(applicability["required"]))
        )

    def test_package_is_offline_and_manifest_complete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            report = builder.build_outputs(output_dir)
            self.assertEqual(report["new_tool_entries_created"], 0)
            self.assertEqual(report["external_api_calls"], 0)
            self.assertFalse(report["formal_pool_generation_allowed"])
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["artifact_count"], 5)
            for artifact in manifest["artifacts"]:
                path = output_dir / artifact["filename"]
                self.assertEqual(builder.sha256_file(path), artifact["sha256"])


if __name__ == "__main__":
    unittest.main()
