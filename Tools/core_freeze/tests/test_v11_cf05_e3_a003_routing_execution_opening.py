import copy
import json
import shutil
import unittest
import uuid

from Tools.core_freeze.e3_routing import (
    build_e3_a003_routing_execution_opening as builder,
)


class V11Cf05E3A003RoutingExecutionOpeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = builder.load_json(builder.CONFIG_PATH)
        cls.built = builder.build(cls.config)

    def test_every_input_and_candidate_artifact_is_hash_bound(self):
        for binding in self.config["bindings"].values():
            builder.validate_binding(binding)

    def test_four_method_grid_is_complete(self):
        preflight = self.built["preflight"]
        self.assertEqual(preflight["opening_status"], "prepared_eligible_pending_explicit_authorization")
        self.assertTrue(all(preflight["checks"].values()))
        self.assertEqual(
            {row["method"]: row["cell_count"] for row in preflight["methods"]},
            {
                "full_schema": 24,
                "lexical_top5": 24,
                "dense_top5": 24,
                "hierarchical": 24,
            },
        )

    def test_schema_views_and_blueprints_are_pool_constrained(self):
        views = {
            row["schema_view_id"]: row for row in self.built["schema_views"]["views"]
        }
        self.assertEqual(len(views), 45)
        cells = self.built["blueprints"]["cells"]
        self.assertEqual(len(cells), 96)
        pools = builder.load_json(
            builder.validate_binding(self.config["bindings"]["selected_pools"])
        )
        pool_by_id = {row["pool_id"]: row for row in pools["pools"]}
        for cell in cells:
            view = views[cell["schema_view_id"]]
            self.assertEqual(view["schema_sha256"], cell["schema_view_sha256"])
            self.assertEqual(view["tool_ids"], cell["selected_tool_ids"])
            self.assertTrue(set(view["tool_ids"]).issubset(pool_by_id[cell["pool_id"]]["tool_order"]))
            expected = cell["tool_pool_size"] if cell["method"] == "full_schema" else 5
            self.assertEqual(view["tool_count"], expected)

    def test_each_request_body_hash_can_be_reconstructed(self):
        prompt = builder.load_json(
            builder.validate_binding(self.config["bindings"]["selector_prompt"])
        )
        views = {
            row["schema_view_id"]: row for row in self.built["schema_views"]["views"]
        }
        for cell in self.built["blueprints"]["cells"]:
            material = cell["request_body_materialization"]
            body = {
                "model": material["model"],
                "messages": [
                    {"role": "system", "content": prompt["system"]},
                    {"role": "user", "content": material["user_problem_text"]},
                ],
                "tools": views[cell["schema_view_id"]]["tools"],
                "tool_choice": material["tool_choice"],
                "temperature": material["temperature"],
                "max_tokens": material["max_tokens"],
            }
            self.assertEqual(builder.json_hash(body), cell["request_body_sha256"])
            self.assertEqual(cell["adapter_settings"], {"thinking": "disabled"})

    def test_router_material_is_gold_and_secret_blind(self):
        serialized = builder.canonical_json(
            {"views": self.built["schema_views"], "blueprints": self.built["blueprints"]}
        )
        for field in (
            "acceptable_tools",
            "revalidated_primary_acceptable_tools",
            "scoring_rule",
            "expected_parameters",
            "target_tool_id",
        ):
            self.assertNotIn(f'"{field}"', serialized)
        self.assertNotIn("api_key", serialized.casefold())

    def test_external_execution_is_not_self_authorized(self):
        authorization = self.built["authorization_request"]
        self.assertTrue(authorization["eligible_for_external_execution_authorization"])
        self.assertFalse(authorization["external_data_sharing_authorized"])
        self.assertFalse(authorization["external_api_execution_authorized"])
        self.assertFalse(authorization["tool_execution_allowed"])
        self.assertEqual(self.built["blueprints"]["external_api_calls"], 0)

    def test_policy_mutations_are_rejected(self):
        for field in (
            "external_api_calls_authorized",
            "external_data_sharing_authorized",
            "tool_execution_allowed",
            "confirmatory_inference_allowed",
            "independent_validation_split_access_allowed",
            "gold_visible_to_router",
            "core_frozen",
        ):
            invalid = copy.deepcopy(self.config)
            invalid[field] = True
            with self.assertRaisesRegex(ValueError, "must remain false"):
                builder.build(invalid)

    def test_fresh_output_manifest_is_hash_complete(self):
        output_dir = (
            builder.WORKSPACE / "outputs" / f".a003-routing-opening-test-{uuid.uuid4().hex}"
        )
        try:
            builder.build_outputs(output_dir)
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["artifact_count"], 5)
            for row in manifest["artifacts"]:
                path = output_dir / row["filename"]
                self.assertEqual(builder.sha256_file(path), row["sha256"])
                self.assertEqual(path.stat().st_size, row["bytes"])
        finally:
            if output_dir.exists():
                shutil.rmtree(output_dir)


if __name__ == "__main__":
    unittest.main()
