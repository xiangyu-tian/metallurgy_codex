import copy
import json
import shutil
import unittest
import uuid
from pathlib import Path

from Tools.core_freeze.e3_routing import review_e3_a003_controlled_pools as reviewer


class V11Cf05E3A003IndependentReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = reviewer.load_json(reviewer.CONFIG_PATH)
        cls.result = reviewer.build(cls.config)

    def test_bound_inputs_are_hash_locked(self):
        for binding in self.config["bindings"].values():
            reviewer.validate_binding(binding)

    def test_relation_categories_are_independently_separated(self):
        rows = self.result["relation_rows"]
        self.assertEqual(len(rows), 16)
        self.assertEqual(sum(row["relation_type"] == "lexical" for row in rows), 8)
        self.assertEqual(
            sum(row["relation_type"] == "contract_mismatch" for row in rows), 8
        )
        self.assertTrue(all(row["review_passed"] for row in rows))

    def test_candidate_runtime_evidence_has_success_and_failure(self):
        candidate_rows = [
            row for row in self.result["relation_rows"] if row["candidate_tool_id"].startswith("E3C")
        ]
        self.assertTrue(candidate_rows)
        for row in candidate_rows:
            runtime = row["runtime_checks"]
            self.assertGreaterEqual(runtime["case_count"], 2)
            self.assertTrue(runtime["all_contract_outcomes_passed"])
            self.assertTrue(runtime["success_case_present"])
            self.assertTrue(runtime["failure_case_present"])

    def test_pool_grid_is_recomputed_not_trusted(self):
        audit = self.result["pool_review"]
        self.assertEqual(audit["record_count"], 100)
        self.assertEqual(audit["expected_grid_cell_count"], 100)
        self.assertTrue(audit["independent_pool_review_passed"])

    def test_task_gold_freshness_gate_blocks_routing(self):
        audit = self.result["task_gold"]
        self.assertEqual(audit["bound_a003_task_count"], 12)
        self.assertEqual(audit["singleton_acceptable_tool_count"], 12)
        self.assertTrue(audit["acceptable_tool_set_revalidation_required"])
        self.assertEqual(
            [row["candidate_tool_id"] for row in audit["new_direct_contract_overlap_candidates"]],
            ["E3C004"],
        )
        self.assertFalse(self.result["report"]["development_routing_run_allowed"])

    def test_policy_escalations_are_rejected(self):
        for field in (
            "development_routing_run_allowed",
            "confirmatory_use_allowed",
            "external_api_calls_authorized",
            "core_frozen",
        ):
            invalid = copy.deepcopy(self.config)
            invalid[field] = True
            with self.assertRaisesRegex(ValueError, "must remain false"):
                reviewer.build(invalid)

    def test_relation_mutation_is_rejected(self):
        invalid = copy.deepcopy(self.config)
        invalid["expected_contract_mismatch_neighbor_ids"][-1] = "E3C019"
        with self.assertRaisesRegex(ValueError, "assignment changed"):
            reviewer.build(invalid)

    def test_fresh_output_manifest_is_complete(self):
        output_dir = reviewer.WORKSPACE / f".test-cf05-a003-review-{uuid.uuid4().hex}"
        try:
            report = reviewer.build_outputs(output_dir)
            self.assertEqual(
                report["status"],
                "pool_and_relation_review_passed_task_gold_revalidation_required",
            )
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["artifact_count"], 5)
            for row in manifest["artifacts"]:
                path = output_dir / row["filename"]
                self.assertEqual(reviewer.sha256_file(path), row["sha256"])
                self.assertEqual(path.stat().st_size, row["bytes"])
        finally:
            if output_dir.exists():
                shutil.rmtree(output_dir)


if __name__ == "__main__":
    unittest.main()
