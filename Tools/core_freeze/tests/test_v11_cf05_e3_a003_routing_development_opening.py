import copy
import json
import shutil
import unittest
import uuid
from pathlib import Path

from Tools.core_freeze.e3_routing import (
    build_e3_a003_routing_development_opening as builder,
)


class V11Cf05E3A003RoutingDevelopmentOpeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = builder.load_json(builder.CONFIG_PATH)
        cls.prompt = builder.load_json(builder.PROMPT_PATH)
        cls.built = builder.build(cls.config, cls.prompt)

    def test_all_bound_inputs_are_hash_valid(self):
        for binding in self.config["bindings"].values():
            builder.validate_binding(binding)

    def test_balanced_96_cell_grid_is_frozen(self):
        cells = self.built["run_cells"]["cells"]
        self.assertEqual(len(cells), 96)
        self.assertEqual(len({row["cell_id"] for row in cells}), 96)
        for method in builder.EXPECTED_METHODS:
            self.assertEqual(sum(row["method"] == method for row in cells), 24)
        for neighbor_type, count in builder.EXPECTED_CONDITIONS:
            self.assertEqual(
                sum(
                    row["near_neighbor_type"] == neighbor_type
                    and row["near_neighbor_count"] == count
                    for row in cells
                ),
                32,
            )

    def test_strict_and_loose_gold_are_separate_from_router_inputs(self):
        visible = self.built["input_tasks"]
        hidden = self.built["scoring_registry"]
        self.assertTrue(visible["router_visible"])
        self.assertFalse(hidden["router_visible"])
        self.assertNotIn("acceptable_tools", builder.canonical_json(visible))
        self.assertEqual(hidden["tasks"][0]["acceptable_tools"], ["A003"])
        self.assertEqual(
            hidden["tasks"][1]["acceptable_tools"], ["A003", "E3C004"]
        )

    def test_selected_pool_grid_has_exact_endpoints_and_core_conditions(self):
        pools = self.built["selected_pools"]["pools"]
        self.assertEqual(len(pools), 12)
        self.assertEqual({row["tool_pool_size"] for row in pools}, {17, 120})
        self.assertEqual({row["pool_repeat"] for row in pools}, {"A", "B"})
        self.assertEqual(
            {
                (row["near_neighbor_type"], row["near_neighbor_count"])
                for row in pools
            },
            set(builder.EXPECTED_CONDITIONS),
        )
        for row in pools:
            self.assertEqual(len(row["tool_order"]), row["tool_pool_size"])
            self.assertIn("A003", row["tool_order"])
            self.assertFalse(row["confirmatory_use_allowed"])

    def test_readiness_gate_blocks_external_execution(self):
        readiness = self.built["method_readiness"]
        status = {
            row["method"]: row["implementation_status"]
            for row in readiness["methods"]
        }
        self.assertEqual(status["full_schema"], "ready")
        self.assertNotEqual(status["lexical_top5"], "ready")
        self.assertNotEqual(status["dense_top5"], "ready")
        self.assertNotEqual(status["hierarchical"], "ready")
        self.assertFalse(readiness["all_methods_ready"])
        self.assertFalse(readiness["external_execution_gate_open"])
        self.assertEqual(self.built["preflight"]["external_api_calls"], 0)

    def test_policy_mutations_are_rejected(self):
        for field in (
            "tool_execution_allowed",
            "external_api_calls_authorized",
            "confirmatory_inference_allowed",
            "formal_pool_use_allowed",
            "gold_visible_to_router",
            "independent_validation_split_access_allowed",
            "core_frozen",
        ):
            invalid = copy.deepcopy(self.config)
            invalid[field] = True
            with self.assertRaisesRegex(ValueError, "must remain false"):
                builder.build(invalid, self.prompt)

    def test_design_mutations_are_rejected(self):
        invalid = copy.deepcopy(self.config)
        invalid["selected_pool_sizes"] = [17, 50, 120]
        with self.assertRaisesRegex(ValueError, "17/120 endpoints"):
            builder.build(invalid, self.prompt)
        invalid = copy.deepcopy(self.config)
        invalid["methods"] = ["full_schema", "hierarchical"]
        with self.assertRaisesRegex(ValueError, "four preregistered"):
            builder.build(invalid, self.prompt)

    def test_output_manifest_is_complete_and_authorization_remains_pending(self):
        output_dir = (
            builder.WORKSPACE
            / "outputs"
            / f".a003-routing-opening-test-{uuid.uuid4().hex}"
        )
        try:
            builder.build_outputs(output_dir)
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["artifact_count"], 9)
            for row in manifest["artifacts"]:
                path = output_dir / row["filename"]
                self.assertTrue(path.is_file())
                self.assertEqual(builder.sha256_file(path), row["sha256"])
                self.assertEqual(path.stat().st_size, row["bytes"])
            request = json.loads(
                (output_dir / "execution_authorization_request.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(request["decision"], "pending_not_eligible")
            self.assertFalse(request["external_api_execution_authorized"])
            self.assertFalse(request["request_payloads_materialized"])
        finally:
            if output_dir.exists():
                shutil.rmtree(output_dir)


if __name__ == "__main__":
    unittest.main()
