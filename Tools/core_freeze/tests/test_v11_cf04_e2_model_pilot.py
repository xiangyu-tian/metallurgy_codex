import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Tools.core_freeze.e2_contract_boundaries.run_e2_development import (
    AUTHORIZATION_PATH,
    CONFIG_PATH,
    CONTRACTS_PATH,
    OUTPUT_SCHEMA_PATH,
    POLICY_PATH,
    PROMPTS_PATH,
    TASKS_PATH,
    build_messages,
    file_hash,
    load_json,
    run_experiment,
    score_prediction,
    validate_inputs,
    validate_execution_authorization,
    validate_output,
    write_outputs,
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

    def configuration(self):
        return {
            "provider": "fake",
            "model": "deepseek-v4-flash",
            "api_key_configured": False,
        }


class V11Cf04E2ModelPilotTests(unittest.TestCase):
    def _inputs(self):
        return (
            load_json(TASKS_PATH),
            load_json(CONTRACTS_PATH),
            load_json(PROMPTS_PATH),
            load_json(OUTPUT_SCHEMA_PATH),
            load_json(POLICY_PATH),
            load_json(CONFIG_PATH),
        )

    def test_frozen_inputs_are_hash_bound_and_nonconfirmatory(self):
        values = self._inputs()
        validate_inputs(*values)
        config = values[-1]
        self.assertEqual(config["task_source_sha256"], file_hash(TASKS_PATH))
        self.assertEqual(config["prompt_sha256"], file_hash(PROMPTS_PATH))
        self.assertEqual(
            config["output_schema_sha256"],
            file_hash(OUTPUT_SCHEMA_PATH),
        )
        self.assertEqual(config["tool_access"], "disabled")
        self.assertFalse(config["confirmatory_inference_allowed"])

    def test_execution_authorization_binds_exact_development_run(self):
        config = load_json(CONFIG_PATH)
        authorization = load_json(AUTHORIZATION_PATH)
        validate_execution_authorization(authorization, config)
        tampered = dict(authorization)
        tampered["authorized_task_count"] = 54
        with self.assertRaises(ValueError):
            validate_execution_authorization(tampered, config)

    def test_prompt_does_not_leak_mutations_or_expected_labels(self):
        tasks, contracts, prompts, _, _, _ = self._inputs()
        contracts_by_tool = {
            row["tool_id"]: row for row in contracts["contracts"]
        }
        task = tasks["tasks"][10]
        messages = build_messages(
            task,
            contracts_by_tool[task["source_tool_id"]],
            prompts,
        )
        text = json.dumps(messages, ensure_ascii=False)
        self.assertNotIn("mutation_types", text)
        self.assertNotIn("expected_flags", text)
        self.assertNotIn(task["task_id"], text)

    def test_output_schema_rejects_extra_or_unknown_fields(self):
        schema = load_json(OUTPUT_SCHEMA_PATH)
        valid = {
            "flags": ["missing_parameter"],
            "primary_status": "missing_or_ambiguous_input",
            "action": "clarify",
        }
        self.assertEqual(validate_output(valid, schema), (True, []))
        invalid = {**valid, "explanation": "leak"}
        self.assertFalse(validate_output(invalid, schema)[0])
        invalid_flag = {
            **valid,
            "flags": ["subjective_boundary"],
        }
        self.assertFalse(validate_output(invalid_flag, schema)[0])

    def test_scoring_preserves_multilabel_exactness(self):
        tasks = load_json(TASKS_PATH)["tasks"]
        schema = load_json(OUTPUT_SCHEMA_PATH)
        task = next(
            row for row in tasks if len(row["expected_flags"]) == 2
        )
        perfect = {
            "flags": list(reversed(task["expected_flags"])),
            "primary_status": task["primary_status"],
            "action": task["policy_expected_action"],
        }
        result = score_prediction(perfect, task, schema)
        self.assertTrue(result["flags_exact"])
        self.assertEqual(result["flags_jaccard"], 1.0)
        missing_one = {**perfect, "flags": task["expected_flags"][:1]}
        result = score_prediction(missing_one, task, schema)
        self.assertFalse(result["flags_exact"])
        self.assertEqual(result["flags_jaccard"], 0.5)

    def test_offline_perfect_run_scores_all_55_tasks(self):
        tasks = load_json(TASKS_PATH)["tasks"]
        outputs = [
            {
                "flags": task["expected_flags"],
                "primary_status": task["primary_status"],
                "action": task["policy_expected_action"],
            }
            for task in tasks
        ]
        adapter = FakeAdapter(outputs)
        records, summary = run_experiment(adapter)
        self.assertEqual(len(records), 55)
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["flags_exact_accuracy"], 1.0)
        self.assertEqual(summary["supported_flag_macro_f1"], 1.0)
        self.assertEqual(summary["action_accuracy"], 1.0)
        self.assertEqual(summary["invalid_execution_rate"], 0.0)

    def test_run_experiment_enforces_execution_authorization(self):
        tasks = load_json(TASKS_PATH)["tasks"]
        adapter = FakeAdapter(
            [
                {
                    "flags": task["expected_flags"],
                    "primary_status": task["primary_status"],
                    "action": task["policy_expected_action"],
                }
                for task in tasks
            ]
        )
        target = (
            "Tools.core_freeze.e2_contract_boundaries."
            "run_e2_development.validate_execution_authorization"
        )
        with patch(target) as validator:
            run_experiment(adapter)
        validator.assert_called_once()

    def test_output_package_has_hashes_and_no_secret(self):
        tasks = load_json(TASKS_PATH)["tasks"]
        adapter = FakeAdapter(
            [
                {
                    "flags": task["expected_flags"],
                    "primary_status": task["primary_status"],
                    "action": task["policy_expected_action"],
                }
                for task in tasks
            ]
        )
        records, summary = run_experiment(adapter)
        config = load_json(CONFIG_PATH)
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "run"
            report = write_outputs(
                output_dir=output_dir,
                records=records,
                summary=summary,
                config=config,
                adapter_configuration=adapter.configuration(),
            )
            self.assertFalse(report["confirmatory_inference_allowed"])
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            for row in manifest["artifacts"]:
                path = output_dir / row["filename"]
                self.assertEqual(file_hash(path), row["sha256"])
            combined = "\n".join(
                path.read_text(encoding="utf-8")
                for path in output_dir.iterdir()
                if path.is_file()
            )
            self.assertNotIn("sk-", combined)


if __name__ == "__main__":
    unittest.main()
