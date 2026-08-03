import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

from Tools.core_freeze.e3_routing import build_e3_source_candidate_batch as builder


class V11Cf05E3SourceCandidateBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batch = builder.load_json(builder.SOURCE_PATH)
        cls.result = builder.validate_batch(cls.batch)

    def test_batch_uses_only_official_primary_documentation(self):
        sources = self.result["registry"]["sources"]
        self.assertEqual(len(sources), 10)
        self.assertTrue(all(row["source_type"] == "primary_documentation" for row in sources))
        self.assertTrue(
            all(
                urlparse(row["locator"]).scheme == "https"
                and urlparse(row["locator"]).hostname in builder.ALLOWED_SOURCE_HOSTS
                for row in sources
            )
        )

    def test_candidates_cover_each_target_without_admission(self):
        report = self.result["precheck"]
        self.assertEqual(report["candidate_count"], 20)
        self.assertEqual(
            report["candidate_count_by_target"],
            {"A001": 2, "A002": 4, "A003": 4, "A004": 5, "B019": 5},
        )
        self.assertEqual(report["accepted_candidate_count"], 0)
        self.assertEqual(report["catalog_increment_count"], 0)
        self.assertEqual(report["filled_relation_slot_count"], 0)

    def test_all_candidates_remain_pending_and_non_executable(self):
        for row in self.result["registry"]["candidates"]:
            self.assertEqual(row["candidate_status"], "source_bound_candidate_unreviewed")
            self.assertEqual(row["relation_claim_status"], "proposed_pending_fixture")
            self.assertEqual(row["independence_status"], "pending")
            self.assertFalse(row["count_toward_catalog"])
            self.assertFalse(row["execution_allowed"])
            self.assertTrue(row["known_limitation"])
            self.assertTrue(row["disqualifier_risk"])

    def test_source_and_candidate_identifiers_are_unique(self):
        registry = self.result["registry"]
        source_ids = [row["source_id"] for row in registry["sources"]]
        candidate_ids = [row["provisional_candidate_id"] for row in registry["candidates"]]
        capability_names = [row["capability_name"] for row in registry["candidates"]]
        self.assertEqual(len(source_ids), len(set(source_ids)))
        self.assertEqual(len(candidate_ids), len(set(candidate_ids)))
        self.assertEqual(len(capability_names), len(set(capability_names)))

    def test_gap_counts_are_not_reduced_by_discovery(self):
        report = self.result["precheck"]
        self.assertEqual(report["remaining_lexical_gap"], 30)
        self.assertEqual(report["remaining_contract_mismatch_gap"], 40)
        self.assertEqual(report["external_api_calls"], 0)
        self.assertFalse(report["formal_pool_generation_allowed"])
        self.assertFalse(report["core_frozen"])

    def test_output_manifest_is_complete_and_reproducible(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            builder.build_outputs(output_dir)
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["artifact_count"], 4)
            self.assertEqual(
                {row["filename"] for row in manifest["artifacts"]},
                {
                    "source_candidate_registry.json",
                    "source_manifest.json",
                    "candidate_precheck_report.json",
                    "source_candidate_batch_snapshot.json",
                },
            )
            for artifact in manifest["artifacts"]:
                path = output_dir / artifact["filename"]
                self.assertEqual(builder.sha256_file(path), artifact["sha256"])


if __name__ == "__main__":
    unittest.main()
