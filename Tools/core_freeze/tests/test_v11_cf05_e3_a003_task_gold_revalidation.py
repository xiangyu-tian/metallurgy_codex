import copy
import json
import shutil
import unittest
import uuid

from Tools.core_freeze.e3_routing import revalidate_e3_a003_task_gold as revalidator


def fake_invoke(_tool_id, params):
    values = {
        "Fe2O3": 159.6882,
        "H2SO4": 98.07848,
        "CaCO3": 100.0869,
        "Fe3O4": 231.5326,
        "CuSO4": 159.6086,
        "(NH4)2SO4": 132.13952,
    }
    return {
        "success": True,
        "result": {"molar_mass": values[params["formula"]], "unit": "g/mol"},
        "error_code": None,
        "error": None,
    }


class V11Cf05E3A003TaskGoldRevalidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = revalidator.load_json(revalidator.CONFIG_PATH)
        cls.result = revalidator.build(
            cls.config,
            invoke_fn=fake_invoke,
            validate_runtime_environment=False,
        )

    def test_bound_inputs_are_hash_locked(self):
        for binding in self.config["bindings"].values():
            revalidator.validate_binding(binding)

    def test_all_a003_tasks_are_revalidated(self):
        self.assertEqual(self.result["report"]["task_count"], 12)
        self.assertEqual(len(self.result["task_rows"]), 12)
        self.assertEqual(len(self.result["execution_rows"]), 12)

    def test_frozen_tolerance_changes_the_acceptable_set(self):
        strict = self.result["task_rows"][0::2]
        loose = self.result["task_rows"][1::2]
        self.assertTrue(
            all(row["revalidated_primary_acceptable_tools"] == ["A003"] for row in strict)
        )
        self.assertTrue(
            all(
                row["revalidated_primary_acceptable_tools"] == ["A003", "E3C004"]
                for row in loose
            )
        )
        self.assertEqual(self.result["report"]["singleton_acceptable_set_count"], 6)
        self.assertEqual(self.result["report"]["multiple_acceptable_set_count"], 6)

    def test_derived_tools_do_not_silently_enter_primary_gold(self):
        for row in self.result["task_rows"]:
            self.assertFalse(row["derived_or_multi_step_tools_primary_acceptable"])
            self.assertTrue(row["alternative_success_must_be_reported"])
            self.assertFalse(
                set(row["derived_or_multi_step_neighbor_ids"])
                & set(row["revalidated_primary_acceptable_tools"])
            )

    def test_wrong_unit_is_not_directly_acceptable(self):
        def wrong_unit(_tool_id, _params):
            return {
                "success": True,
                "result": {"molar_mass": 159.687, "unit": "u"},
                "error_code": None,
                "error": None,
            }

        task = self.result["task_rows"][0]
        source = {
            "task_id": task["task_id"],
            "canonical_inputs": task["canonical_inputs"],
            "scoring_rule": task["scoring_rule"],
        }
        evaluated = revalidator.evaluate_candidate(
            source, "E3C004", self.config, wrong_unit
        )
        self.assertFalse(evaluated["directly_acceptable"])

    def test_policy_escalations_are_rejected(self):
        invalid = copy.deepcopy(self.config)
        invalid["confirmatory_use_allowed"] = True
        with self.assertRaisesRegex(ValueError, "must remain false"):
            revalidator.build(
                invalid,
                invoke_fn=fake_invoke,
                validate_runtime_environment=False,
            )
        invalid = copy.deepcopy(self.config)
        invalid["derived_or_multi_step_tools_primary_acceptable"] = True
        with self.assertRaisesRegex(ValueError, "cannot silently enter"):
            revalidator.build(
                invalid,
                invoke_fn=fake_invoke,
                validate_runtime_environment=False,
            )

    def test_fresh_output_manifest_is_complete_with_fake_runtime(self):
        output_dir = revalidator.WORKSPACE / f".test-cf05-a003-gold-{uuid.uuid4().hex}"
        original_build = revalidator.build
        try:
            revalidator.build = lambda config: original_build(
                config,
                invoke_fn=fake_invoke,
                validate_runtime_environment=False,
            )
            report = revalidator.build_outputs(output_dir)
            self.assertTrue(report["development_routing_run_allowed"])
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["artifact_count"], 4)
            for row in manifest["artifacts"]:
                path = output_dir / row["filename"]
                self.assertEqual(revalidator.sha256_file(path), row["sha256"])
        finally:
            revalidator.build = original_build
            if output_dir.exists():
                shutil.rmtree(output_dir)


if __name__ == "__main__":
    unittest.main()
