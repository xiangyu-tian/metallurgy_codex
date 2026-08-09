import copy
import json
import shutil
import unittest
import uuid

from Tools.core_freeze.e3_routing import (
    build_e3_a003_hierarchical_top5_candidate as builder,
)


class V11Cf05E3A003HierarchicalTop5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = builder.load_json(builder.CONFIG_PATH)
        cls.built = builder.build(cls.config)

    def test_all_inputs_are_hash_bound(self):
        for binding in self.config["bindings"].values():
            builder.validate_binding(binding)

    def test_taxonomy_covers_registry_without_gold(self):
        taxonomy = self.built["taxonomy"]
        self.assertEqual(taxonomy["tool_count"], 137)
        self.assertEqual(taxonomy["domain_count"], 7)
        self.assertGreater(taxonomy["capability_count"], taxonomy["domain_count"])
        self.assertEqual(len(taxonomy["tool_nodes"]), 137)
        serialized = builder.canonical_json(taxonomy)
        self.assertNotIn("acceptable_tools", serialized)
        self.assertNotIn("scoring_rule", serialized)

    def test_exact_24_hierarchical_pool_constrained_views(self):
        views = self.built["candidate_views"]["views"]
        self.assertEqual(len(views), 24)
        pools = builder.load_json(
            builder.validate_binding(self.config["bindings"]["routing_selected_pools"])
        )
        pool_by_id = {row["pool_id"]: row for row in pools["pools"]}
        for view in views:
            self.assertEqual(len(view["candidate_tool_ids"]), 5)
            self.assertEqual(len(set(view["candidate_tool_ids"])), 5)
            self.assertTrue(
                set(view["candidate_tool_ids"]).issubset(
                    pool_by_id[view["pool_id"]]["tool_order"]
                )
            )
            self.assertLessEqual(len(view["selected_domains"]), 3)
            self.assertLessEqual(len(view["selected_capabilities"]), 8)

    def test_hierarchy_trace_is_deterministic_and_gold_blind(self):
        self.assertTrue(
            self.built["determinism"]["all_repeated_results_equal"]
        )
        serialized = builder.canonical_json(self.built["candidate_views"])
        for field in (
            "acceptable_tools",
            "revalidated_primary_acceptable_tools",
            "scoring_rule",
            "expected_parameters",
        ):
            self.assertNotIn(f'"{field}"', serialized)
        self.assertFalse(self.built["candidate_views"]["router_visible_gold"])

    def test_local_promotion_gate_passes_without_external_calls(self):
        report = self.built["readiness"]
        self.assertEqual(
            report["implementation_status"],
            "candidate_implementation_passed_local_gate",
        )
        self.assertTrue(report["ready_for_24_cell_hierarchical_slice_generation"])
        self.assertFalse(report["ready_for_external_development_run"])
        self.assertEqual(
            report["observed_development_metrics"]["acceptable_recall_at_5"],
            1.0,
        )
        self.assertEqual(
            report["observed_development_metrics"]["target_recall_at_5"], 1.0
        )
        self.assertEqual(self.built["candidate_views"]["external_api_calls"], 0)
        self.assertEqual(self.built["candidate_views"]["tool_calls_executed"], 0)

    def test_policy_and_breadth_mutations_are_rejected(self):
        for field in (
            "gold_visible_to_router",
            "external_api_calls_authorized",
            "tool_execution_allowed",
            "confirmatory_inference_allowed",
            "independent_validation_split_access_allowed",
            "core_frozen",
        ):
            invalid = copy.deepcopy(self.config)
            invalid[field] = True
            with self.assertRaisesRegex(ValueError, "must remain false"):
                builder.build(invalid)
        invalid = copy.deepcopy(self.config)
        invalid["domain_top_n"] = 4
        with self.assertRaisesRegex(ValueError, "hierarchy breadth"):
            builder.build(invalid)

    def test_fresh_output_manifest_is_hash_complete(self):
        output_dir = (
            builder.WORKSPACE
            / "outputs"
            / f".a003-hierarchical-top5-test-{uuid.uuid4().hex}"
        )
        try:
            builder.build_outputs(output_dir)
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["artifact_count"], 6)
            for row in manifest["artifacts"]:
                path = output_dir / row["filename"]
                self.assertEqual(builder.sha256_file(path), row["sha256"])
                self.assertEqual(path.stat().st_size, row["bytes"])
        finally:
            if output_dir.exists():
                shutil.rmtree(output_dir)


if __name__ == "__main__":
    unittest.main()
