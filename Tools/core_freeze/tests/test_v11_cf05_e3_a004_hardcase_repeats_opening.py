import copy
import json
import unittest

from Tools.core_freeze.e3_routing import build_e3_a004_hardcase_repeats_opening as builder


class V11Cf05E3A004HardcaseRepeatsOpeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = builder.load_json(builder.CONFIG_PATH)
        cls.result = builder.build(cls.config)

    def test_bound_r1_evidence_is_immutable(self):
        for binding in self.config["bindings"].values():
            builder.validate_binding(binding)

    def test_exact_r2_r3_grid_preserves_r1_order(self):
        cells = self.result["repeat_cells"]["cells"]
        self.assertEqual(len(cells), 96)
        for repeat in (2, 3):
            subset = [row for row in cells if row["model_run_repeat"] == repeat]
            self.assertEqual(len(subset), 48)
            self.assertTrue(all(row["cell_id"].endswith(f"-R{repeat}") for row in subset))
            self.assertTrue(all(row["execution_status"] == "not_executed" for row in subset))

    def test_pairing_and_volatility_contract_are_complete(self):
        pairs = self.result["pairing_plan"]
        self.assertEqual(pairs["pairing_unit_count"], 48)
        self.assertEqual(pairs["repeats_per_unit"], 3)
        self.assertTrue(all(row["same_task_schema_prompt_retrieval_scoring_required"] for row in pairs["rows"]))
        contract = self.result["volatility_contract"]
        self.assertEqual(contract["r1_observed_failure_count"], 1)
        self.assertFalse(contract["inputs_or_scoring_tuned_after_r1"])
        self.assertFalse(contract["confirmatory_inference_allowed"])

    def test_router_visible_repeat_artifacts_have_no_gold(self):
        public = json.dumps({"tasks": self.result["input_tasks"], "views": self.result["candidate_views"],
                             "cells": self.result["repeat_cells"]}, ensure_ascii=False)
        for field in self.result["selector_prompt"]["gold_fields_forbidden"]:
            self.assertNotIn(f'"{field}"', public)

    def test_no_external_authority_is_inferred(self):
        self.assertEqual(self.result["preflight"]["external_api_calls"], 0)
        self.assertTrue(all(self.result["preflight"]["checks"].values()))
        for field in ("tool_execution_allowed", "provider_retry_allowed", "external_api_calls_authorized",
                      "independent_validation_split_access_allowed", "confirmatory_inference_allowed", "core_frozen"):
            invalid = copy.deepcopy(self.config)
            invalid[field] = True
            with self.assertRaisesRegex(ValueError, "must remain false"):
                builder.build(invalid)

    def test_committed_opening_is_hash_complete(self):
        output_dir = builder.WORKSPACE / "outputs" / "v11_cf05_e3_a004_hardcase_r2r3_opening_v1_20260810"
        preflight = builder.load_json(output_dir / "a004_repeats_opening_preflight.json")
        self.assertEqual(preflight["opening_status"], "prepared_local_gate_passed_pending_external_authorization")
        authorization = builder.load_json(output_dir / "execution_authorization_request.json")
        self.assertFalse(authorization["external_api_execution_authorized"])
        manifest = builder.load_json(output_dir / "artifact_manifest.json")
        self.assertEqual(manifest["artifact_count"], 10)
        for row in manifest["artifacts"]:
            path = output_dir / row["filename"]
            self.assertTrue(path.is_file())
            self.assertEqual(builder.file_hash(path), row["sha256"])


if __name__ == "__main__":
    unittest.main()
