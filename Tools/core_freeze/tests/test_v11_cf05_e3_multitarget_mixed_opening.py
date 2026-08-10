import copy
import json
import unittest

from Tools.core_freeze.e3_routing import build_e3_multitarget_mixed_opening as builder


class FakeRetriever:
    def __init__(self, target_by_query):
        self.target_by_query = target_by_query

    def retrieve(self, query, pool_tool_ids, *, top_k=5):
        target = self.target_by_query[query]
        selected = [target] + [tool_id for tool_id in pool_tool_ids if tool_id != target][: top_k - 1]
        return {
            "algorithm": "test_injected",
            "candidate_pool_size": len(pool_tool_ids),
            "candidates": [
                {"tool_id": tool_id, "score": float(top_k - index), "rank": index + 1}
                for index, tool_id in enumerate(selected)
            ],
        }


class V11Cf05E3MultitargetMixedOpeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = builder.load_json(builder.CONFIG_PATH)
        cls.prompt = builder.load_json(builder.PROMPT_PATH)
        taskset_path = builder.WORKSPACE / cls.config["bindings"]["taskset"]["path"]
        taskset = builder.load_json(taskset_path)
        selected = {
            row["task_id"]: row
            for row in taskset["tasks"]
            if row["task_id"] in cls.config["selected_task_ids"]
        }
        target_by_query = {
            selected[task_id]["problem_text"]: selected[task_id]["source_tool_id"]
            for task_id in cls.config["selected_task_ids"]
        }
        fake = FakeRetriever(target_by_query)
        cls.result = builder.build(
            cls.config,
            cls.prompt,
            retrievers={
                "lexical_top5": fake,
                "dense_top5": fake,
                "hierarchical": fake,
            },
        )

    def test_all_bound_inputs_are_immutable(self):
        for binding in self.config["bindings"].values():
            builder.validate_binding(binding)

    def test_balanced_task_and_pool_endpoints(self):
        self.assertEqual(self.result["input_tasks"]["task_count"], 8)
        scoring = self.result["scoring_registry"]["tasks"]
        self.assertEqual(
            {target: sum(row["source_tool_id"] == target for row in scoring) for target in builder.EXPECTED_TARGETS},
            {"A001": 2, "A002": 2, "A004": 2, "B019": 2},
        )
        self.assertEqual(
            [row["tool_pool_size"] for row in self.result["selected_pools"]["pools"]],
            [17, 120],
        )

    def test_exact_candidate_view_and_cell_grids(self):
        views = self.result["candidate_views"]["views"]
        self.assertEqual(len(views), 50)
        self.assertEqual(sum(row["method"] == "full_schema" for row in views), 2)
        for method in builder.EXPECTED_METHODS[1:]:
            self.assertEqual(sum(row["method"] == method for row in views), 16)
        cells = self.result["run_cells"]["cells"]
        self.assertEqual(len(cells), 64)
        self.assertEqual(len({row["cell_id"] for row in cells}), 64)
        self.assertTrue(all(row["execution_status"] == "not_executed" for row in cells))

    def test_router_visible_artifacts_contain_no_gold_fields(self):
        public = json.dumps(
            {
                "tasks": self.result["input_tasks"],
                "views": self.result["candidate_views"],
                "cells": self.result["run_cells"],
            },
            ensure_ascii=False,
        )
        for field in self.prompt["gold_fields_forbidden"]:
            self.assertNotIn(f'"{field}"', public)
        for view in self.result["candidate_views"]["views"]:
            self.assertEqual(
                len(view["ordered_candidate_tool_ids"]),
                view["tool_pool_size"] if view["method"] == "full_schema" else 5,
            )

    def test_local_gate_is_development_only(self):
        gate = self.result["local_gate"]
        self.assertTrue(gate["all_top5_methods_passed"])
        self.assertFalse(gate["confirmatory_inference_allowed"])
        self.assertTrue(all(row["local_gate_passed"] for row in gate["summaries"]))
        preflight = self.result["preflight"]
        self.assertEqual(
            preflight["opening_status"],
            "prepared_local_gate_passed_pending_external_authorization",
        )
        self.assertEqual(preflight["external_api_calls"], 0)

    def test_policy_escalations_are_rejected(self):
        for field in (
            "tool_execution_allowed",
            "external_api_calls_authorized",
            "confirmatory_inference_allowed",
            "formal_pool_use_allowed",
            "gold_visible_to_router",
            "independent_validation_split_access_allowed",
            "full_137_registry_gold_claim_allowed",
            "core_frozen",
        ):
            invalid = copy.deepcopy(self.config)
            invalid[field] = True
            with self.assertRaisesRegex(ValueError, "must remain false"):
                builder.build(invalid, self.prompt, retrievers={})

    def test_committed_real_output_is_hash_complete(self):
        output_dir = (
            builder.WORKSPACE
            / "outputs"
            / "v11_cf05_e3_multitarget_mixed_opening_v1_20260810"
        )
        preflight = builder.load_json(output_dir / "multitarget_opening_preflight.json")
        self.assertTrue(preflight["checks"]["all_top5_methods_passed_local_recall_gate"])
        authorization = builder.load_json(output_dir / "execution_authorization_request.json")
        self.assertEqual(authorization["decision"], "pending_user_authorization")
        self.assertFalse(authorization["external_api_execution_authorized"])
        manifest = builder.load_json(output_dir / "artifact_manifest.json")
        self.assertEqual(manifest["artifact_count"], 10)
        for row in manifest["artifacts"]:
            path = output_dir / row["filename"]
            self.assertTrue(path.is_file())
            self.assertEqual(builder.sha256_file(path), row["sha256"])


if __name__ == "__main__":
    unittest.main()
