import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Tools.core_freeze.e2_contract_boundaries.run_e2_development import (
    CONTRACTS_PATH,
    POLICY_PATH,
    TASKS_PATH,
    file_hash,
    load_json,
)
from Tools.core_freeze.e2_contract_boundaries.run_e2_development_v1_1 import (
    AUTHORIZATION_PATH,
    CONFIG_PATH,
    OUTPUT_SCHEMA_PATH,
    PROMPTS_PATH,
    derive_policy_decision,
    execute_tasks,
    run_experiment,
    score_flags_prediction,
    validate_execution_authorization,
    validate_flags_output,
    validate_inputs,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CANDIDATE_OUTPUT_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_policy_v1_1_candidate_20260731"
)


class FakeAdapter:
    def __init__(self, outputs):
        self.outputs = iter(outputs)

    def complete(self, messages, **kwargs):
        return {
            "id": "fake",
            "model": "deepseek-v4-flash",
            "message": {
                "role": "assistant",
                "content": json.dumps(
                    next(self.outputs),
                    ensure_ascii=False,
                ),
            },
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        }


class V11Cf04E2PolicyV11Tests(unittest.TestCase):
    def _inputs(self):
        return (
            load_json(TASKS_PATH),
            load_json(CONTRACTS_PATH),
            load_json(PROMPTS_PATH),
            load_json(OUTPUT_SCHEMA_PATH),
            load_json(POLICY_PATH),
            load_json(CONFIG_PATH),
        )

    def test_candidate_is_flags_only_and_hash_bound(self):
        values = self._inputs()
        validate_inputs(*values)
        prompts = values[2]
        schema = values[3]
        self.assertEqual(schema["required"], ["flags"])
        self.assertEqual(set(schema["properties"]), {"flags"})
        self.assertNotIn("primary_status", prompts["output_contract"])
        self.assertNotIn("action", prompts["output_contract"])
        self.assertEqual(values[-1]["execution_status"], "prepared_not_authorized")

    def test_prompt_has_no_answer_leakage_and_defines_distinction(self):
        prompts = load_json(PROMPTS_PATH)
        text = json.dumps(prompts, ensure_ascii=False)
        for forbidden in ("mutation_types", "expected_flags", "task_id"):
            self.assertNotIn(forbidden, text)
        self.assertIn("仍属于该工具声明的系统类型", text)
        self.assertIn("系统类型、相数、组元数", text)
        self.assertIn("同时保留所有成立的flags", text)

    def test_schema_rejects_model_derived_fields(self):
        schema = load_json(OUTPUT_SCHEMA_PATH)
        self.assertEqual(
            validate_flags_output({"flags": []}, schema),
            (True, []),
        )
        valid_flags = {"flags": ["missing_parameter", "unavailable"]}
        self.assertTrue(validate_flags_output(valid_flags, schema)[0])
        self.assertFalse(
            validate_flags_output(
                {**valid_flags, "action": "clarify"},
                schema,
            )[0]
        )
        self.assertFalse(
            validate_flags_output(
                {**valid_flags, "primary_status": "unavailable"},
                schema,
            )[0]
        )

    def test_multilabel_priority_is_deterministically_derived(self):
        policy = load_json(POLICY_PATH)
        primary, action = derive_policy_decision(
            ["unavailable", "ambiguous_parameter"],
            policy,
        )
        self.assertEqual(primary, "missing_or_ambiguous_input")
        self.assertEqual(action, "clarify")
        task = next(
            row
            for row in load_json(TASKS_PATH)["tasks"]
            if set(row["expected_flags"])
            == {"missing_parameter", "unavailable"}
        )
        result = score_flags_prediction(
            {"flags": ["unavailable", "missing_parameter"]},
            task,
            load_json(OUTPUT_SCHEMA_PATH),
            policy,
        )
        self.assertTrue(result["flags_exact"])
        self.assertTrue(result["action_correct"])
        self.assertEqual(
            result["decision_source"],
            "deterministic_policy_from_predicted_flags",
        )

    def test_unsupported_system_remains_distinct_from_in_domain_ood(self):
        tasks = load_json(TASKS_PATH)["tasks"]
        task = next(
            row
            for row in tasks
            if row["mutation_types"] == ["unsupported_system"]
        )
        schema = load_json(OUTPUT_SCHEMA_PATH)
        policy = load_json(POLICY_PATH)
        correct = score_flags_prediction(
            {"flags": ["contract_defined_unsupported_system"]},
            task,
            schema,
            policy,
        )
        confused = score_flags_prediction(
            {"flags": ["contract_defined_out_of_domain"]},
            task,
            schema,
            policy,
        )
        self.assertTrue(correct["flags_exact"])
        self.assertFalse(confused["flags_exact"])
        self.assertTrue(confused["action_correct"])

    def test_offline_perfect_outputs_score_all_55_tasks(self):
        tasks_doc, contracts_doc, prompts, schema, policy, config = (
            self._inputs()
        )
        adapter = FakeAdapter(
            [{"flags": task["expected_flags"]} for task in tasks_doc["tasks"]]
        )
        records, summary = execute_tasks(
            adapter,
            tasks_doc=tasks_doc,
            contracts_doc=contracts_doc,
            prompts=prompts,
            output_schema=schema,
            policy=policy,
            config=config,
        )
        self.assertEqual(len(records), 55)
        self.assertEqual(summary["schema_valid_rate"], 1.0)
        self.assertEqual(summary["flags_exact_accuracy"], 1.0)
        self.assertEqual(summary["action_accuracy"], 1.0)
        self.assertEqual(summary["model_output_fields"], ["flags"])
        self.assertTrue(
            all(
                set(json.loads(row["raw_output"])) == {"flags"}
                for row in records
            )
        )

    def test_authorization_is_bound_and_missing_file_is_rejected(self):
        authorization = load_json(AUTHORIZATION_PATH)
        config = load_json(CONFIG_PATH)
        validate_execution_authorization(authorization, config)
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing_authorization.json"
            target = (
                "Tools.core_freeze.e2_contract_boundaries."
                "run_e2_development_v1_1.AUTHORIZATION_PATH"
            )
            with patch(target, missing):
                with self.assertRaisesRegex(
                    FileNotFoundError,
                    "authorization is pending",
                ):
                    run_experiment(FakeAdapter([]))

    def test_counterfactual_package_is_pending_and_audited(self):
        report = json.loads(
            (CANDIDATE_OUTPUT_DIR / "candidate_report.json").read_text(
                encoding="utf-8"
            )
        )
        replay = report["counterfactual_replay"]
        self.assertEqual(report["status"], "prepared_not_authorized")
        self.assertEqual(replay["new_provider_calls"], 0)
        self.assertFalse(replay["independent_model_recheck_completed"])
        self.assertEqual(replay["schema_valid_rate"], 1.0)
        self.assertEqual(replay["flags_exact_count"], 42)
        self.assertAlmostEqual(
            replay["action_accuracy"],
            50 / 55,
        )
        manifest = json.loads(
            (CANDIDATE_OUTPUT_DIR / "artifact_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            manifest["execution_status"],
            "prepared_not_authorized",
        )
        for artifact in manifest["artifacts"]:
            self.assertEqual(
                file_hash(CANDIDATE_OUTPUT_DIR / artifact["filename"]),
                artifact["sha256"],
            )


if __name__ == "__main__":
    unittest.main()
