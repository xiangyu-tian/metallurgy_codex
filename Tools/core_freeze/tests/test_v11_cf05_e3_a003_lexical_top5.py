import copy
import json
import shutil
import unittest
import uuid

from Tools.core_freeze.e3_routing import build_e3_a003_lexical_top5_candidate as builder
from Tools.core_freeze.e3_routing.lexical_top5_router import tokenize


class V11Cf05E3A003LexicalTop5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = builder.load_json(builder.CONFIG_PATH)
        cls.built = builder.build(cls.config)

    def test_all_inputs_are_hash_bound(self):
        for binding in self.config["bindings"].values():
            builder.validate_binding(binding)

    def test_unicode_tokenizer_is_deterministic_and_ignores_numbers(self):
        tokens = tokenize("计算 Fe2O3 的摩尔质量 159.687", self.config["tokenizer"])
        self.assertIn("lat:fe2o3", tokens)
        self.assertIn("zh2:摩尔", tokens)
        self.assertIn("zh3:摩尔质", tokens)
        self.assertFalse(any(token.startswith("num:") for token in tokens))
        self.assertEqual(tokens, tokenize("计算 Fe2O3 的摩尔质量 159.687", self.config["tokenizer"]))

    def test_index_covers_the_bound_registry(self):
        snapshot = self.built["index_snapshot"]
        self.assertEqual(snapshot["document_count"], 137)
        self.assertEqual(len(snapshot["documents"]), 137)
        self.assertEqual(len(snapshot["index_sha256"]), 64)

    def test_exact_24_pool_constrained_top5_views(self):
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

    def test_gold_is_absent_from_router_candidate_views(self):
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
        self.assertTrue(report["ready_for_24_cell_lexical_slice_generation"])
        self.assertFalse(report["ready_for_external_development_run"])
        self.assertEqual(
            report["observed_development_metrics"]["acceptable_recall_at_5"],
            1.0,
        )
        self.assertEqual(
            report["observed_development_metrics"]["target_recall_at_5"], 1.0
        )
        self.assertTrue(
            self.built["determinism"]["all_repeated_results_equal"]
        )
        self.assertEqual(self.built["candidate_views"]["external_api_calls"], 0)
        self.assertEqual(self.built["candidate_views"]["tool_calls_executed"], 0)

    def test_policy_mutations_are_rejected(self):
        for field in (
            "gold_visible_to_retriever",
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

    def test_fresh_output_manifest_is_hash_complete(self):
        output_dir = (
            builder.WORKSPACE
            / "outputs"
            / f".a003-lexical-top5-test-{uuid.uuid4().hex}"
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
