import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.e3_routing import audit_e3_neighbor_feasibility as audit


class V11Cf05E3NeighborFeasibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = audit.load_json(audit.CONFIG_PATH)
        cls.result = audit.audit(cls.config)

    def test_targets_are_exactly_verified_core(self):
        targets = {
            row["target_tool_id"]
            for row in self.result["candidate_matrix"]["targets"]
        }
        self.assertEqual(targets, {"A001", "A002", "A003", "A004", "B019"})

    def test_no_weak_candidates_are_used_to_fill_eight(self):
        self.assertTrue(self.config["weak_related_fill_forbidden"])
        self.assertTrue(
            all(
                target["provable_contract_mismatch_neighbor_count"] == 0
                for target in self.result["candidate_matrix"]["targets"]
            )
        )
        self.assertEqual(
            self.result["feasibility"]["h3_paired_8_eligible_target_count"],
            0,
        )
        self.assertFalse(
            self.result["feasibility"]["formal_controlled_dose_pools_generated"]
        )

    def test_120_controlled_dose_requires_larger_universe(self):
        row = next(
            item
            for item in self.result["feasibility"]["capacity"]
            if item["tool_pool_size"] == 120
        )
        self.assertEqual(row["single_neighbor_type_min_catalog_size"], 128)
        self.assertEqual(row["two_disjoint_neighbor_types_min_catalog_size"], 136)
        self.assertFalse(row["single_type_capacity_feasible"])
        self.assertFalse(row["two_disjoint_type_capacity_feasible"])

    def test_pair_scores_are_reproducible_and_bounded(self):
        targets = self.result["candidate_matrix"]["targets"]
        self.assertEqual(self.result["candidate_matrix"]["pair_row_count"], 5 * 119)
        for target in targets:
            for row in target["top_screening_rows"]:
                for field in (
                    "name_bigram_dice",
                    "contract_text_bigram_dice",
                    "input_bigram_dice",
                    "output_bigram_dice",
                ):
                    self.assertGreaterEqual(row[field], 0.0)
                    self.assertLessEqual(row[field], 1.0)

    def test_output_package_is_offline_and_manifest_complete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            report = audit.build_outputs(output_dir)
            self.assertEqual(report["external_api_calls"], 0)
            self.assertFalse(report["external_api_calls_authorized"])
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["artifact_count"], 4)
            for artifact in manifest["artifacts"]:
                path = output_dir / artifact["filename"]
                self.assertTrue(path.is_file())
                self.assertEqual(audit.sha256_file(path), artifact["sha256"])


if __name__ == "__main__":
    unittest.main()
