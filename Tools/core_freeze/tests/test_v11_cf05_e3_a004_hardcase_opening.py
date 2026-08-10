import copy
import json
import unittest

from Tools.core_freeze.e3_routing import build_e3_a004_hardcase_opening as builder


class FakeRetriever:
    def retrieve(self, query, pool_tool_ids, *, top_k=5):
        selected = ["A004"] + [tool_id for tool_id in pool_tool_ids if tool_id != "A004"][: top_k - 1]
        return {"algorithm": "test_injected", "candidate_pool_size": len(pool_tool_ids),
                "candidates": [{"tool_id": tool_id, "score": float(top_k - i), "rank": i + 1}
                               for i, tool_id in enumerate(selected)]}


class V11Cf05E3A004HardcaseOpeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = builder.load_json(builder.CONFIG_PATH)
        fake = FakeRetriever()
        cls.result = builder.build(cls.config, retrievers={
            "lexical_top5": fake, "dense_top5": fake, "hierarchical": fake,
        })

    def test_bound_inputs_and_frozen_policy(self):
        for binding in self.config["bindings"].values():
            builder.validate_binding(binding)
        self.assertFalse(self.config["external_api_calls_authorized"])
        self.assertFalse(self.config["confirmatory_inference_allowed"])
        self.assertFalse(self.config["formal_pool_use_allowed"])

    def test_tasks_are_a004_only_hard_cases(self):
        self.assertEqual([row["task_id"] for row in self.result["input_tasks"]["tasks"]],
                         ["E1B2-A004-007", "E1B2-A004-008"])
        self.assertTrue(all(row["acceptable_tools_development_scope"] == ["A004"]
                            for row in self.result["scoring_registry"]["tasks"]))

    def test_relation_evidence_is_exactly_four_plus_four(self):
        evidence = self.result["relation_evidence"]
        self.assertEqual((evidence["lexical_count"], evidence["contract_mismatch_count"]), (4, 4))
        self.assertTrue(all(row["relation_evidence_passed"] for row in evidence["relations"]))

    def test_controlled_pools_are_nested_and_uncontaminated(self):
        pools = {(row["condition_id"], row["tool_pool_size"]): row
                 for row in self.result["selected_pools"]["pools"]}
        self.assertEqual(len(pools), 6)
        lexical = set(self.config["neighbor_conditions"][1]["tool_ids"])
        mismatch = set(self.config["neighbor_conditions"][2]["tool_ids"])
        self.assertFalse(set(pools[("none_0", 120)]["tool_order"]) & (lexical | mismatch))
        self.assertEqual(set(pools[("lexical_4", 120)]["tool_order"]) & (lexical | mismatch), lexical)
        self.assertEqual(set(pools[("contract_mismatch_4", 120)]["tool_order"]) & (lexical | mismatch), mismatch)
        for condition in builder.EXPECTED_CONDITIONS:
            self.assertTrue(set(pools[(condition, 17)]["tool_order"]).issubset(pools[(condition, 120)]["tool_order"]))

    def test_view_and_cell_grids_are_complete(self):
        self.assertEqual(self.result["candidate_views"]["candidate_view_count"], 42)
        self.assertEqual(self.result["run_cells"]["cell_count"], 48)
        self.assertEqual(len({row["cell_id"] for row in self.result["run_cells"]["cells"]}), 48)

    def test_router_visible_artifacts_have_no_gold(self):
        public = json.dumps({"tasks": self.result["input_tasks"], "pools": self.result["selected_pools"],
                             "views": self.result["candidate_views"], "cells": self.result["run_cells"]},
                            ensure_ascii=False)
        for field in self.result["prompt"]["gold_fields_forbidden"]:
            self.assertNotIn(f'"{field}"', public)

    def test_policy_escalations_are_rejected(self):
        for field in ("tool_execution_allowed", "external_api_calls_authorized",
                      "confirmatory_inference_allowed", "formal_pool_use_allowed",
                      "gold_visible_to_router", "independent_validation_split_access_allowed",
                      "full_registry_gold_claim_allowed", "core_frozen"):
            invalid = copy.deepcopy(self.config)
            invalid[field] = True
            with self.assertRaisesRegex(ValueError, "must remain false"):
                builder.build(invalid, retrievers={})

    def test_committed_real_output_is_hash_complete(self):
        output_dir = builder.WORKSPACE / "outputs" / "v11_cf05_e3_a004_hardcase_opening_v1_20260810"
        preflight = builder.load_json(output_dir / "a004_opening_preflight.json")
        self.assertEqual(preflight["opening_status"],
                         "prepared_local_gate_passed_pending_external_authorization")
        self.assertTrue(all(preflight["checks"].values()))
        authorization = builder.load_json(output_dir / "execution_authorization_request.json")
        self.assertEqual(authorization["decision"], "pending_user_authorization")
        self.assertFalse(authorization["external_api_execution_authorized"])
        manifest = builder.load_json(output_dir / "artifact_manifest.json")
        self.assertEqual(manifest["artifact_count"], 12)
        for row in manifest["artifacts"]:
            path = output_dir / row["filename"]
            self.assertTrue(path.is_file())
            self.assertEqual(builder.sha256_file(path), row["sha256"])


if __name__ == "__main__":
    unittest.main()
