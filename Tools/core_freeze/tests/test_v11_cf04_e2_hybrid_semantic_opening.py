import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Tools.core_freeze.e2_contract_boundaries.build_e2_hybrid_semantic_opening import (
    audit_model_payloads,
    build_package,
    validate_opening,
)
from Tools.core_freeze.e2_contract_boundaries.run_e2_development import (
    file_hash,
    load_json,
)
from Tools.core_freeze.e2_contract_boundaries.run_e2_hybrid_semantic_development import (
    BASE_POLICY_PATH,
    CONFIG_PATH,
    CONTRACTS_PATH,
    HYBRID_POLICY_PATH,
    OUTPUT_SCHEMA_PATH,
    PROMPTS_PATH,
    TASKS_PATH,
    execute_tasks,
    expected_semantic_flags,
    run_experiment,
    score_semantic_prediction,
    validate_inputs,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_hybrid_semantic_dev_opening_v1_20260731"
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


class V11Cf04E2HybridSemanticOpeningTests(unittest.TestCase):
    def _inputs(self):
        return (
            load_json(TASKS_PATH),
            load_json(CONTRACTS_PATH),
            load_json(PROMPTS_PATH),
            load_json(OUTPUT_SCHEMA_PATH),
            load_json(BASE_POLICY_PATH),
            load_json(HYBRID_POLICY_PATH),
            load_json(CONFIG_PATH),
        )

    def test_opening_validates_bound_sources_and_pending_gate(self):
        values = validate_opening()
        validate_inputs(*self._inputs())
        self.assertEqual(values["tasks"]["task_count"], 55)
        self.assertEqual(
            values["config"]["execution_status"],
            "prepared_not_authorized",
        )
        self.assertFalse(
            values["authorization_request"][
                "external_api_execution_authorized"
            ]
        )

    def test_payload_audit_excludes_gold_and_identifiers(self):
        audit = audit_model_payloads(validate_opening())
        self.assertEqual(audit["status"], "passed")
        self.assertEqual(audit["task_count"], 55)
        self.assertEqual(audit["leakage_error_count"], 0)
        self.assertFalse(audit["gold_labels_sent"])
        self.assertFalse(audit["mutation_history_sent"])
        self.assertFalse(audit["validation_dataset_sent"])

    def test_semantic_schema_rejects_structural_flag(self):
        (
            tasks,
            contracts,
            _prompts,
            schema,
            base_policy,
            hybrid_policy,
            _config,
        ) = self._inputs()
        task = tasks["tasks"][0]
        contract = next(
            row
            for row in contracts["contracts"]
            if row["tool_id"] == task["source_tool_id"]
        )
        score = score_semantic_prediction(
            {"semantic_flags": ["missing_parameter"]},
            task,
            contract,
            schema,
            base_policy,
            hybrid_policy,
        )
        self.assertFalse(score["semantic_schema_valid"])
        self.assertFalse(score["action_correct"])

    def test_offline_perfect_semantic_outputs_score_all_tasks(self):
        (
            tasks,
            contracts,
            prompts,
            schema,
            base_policy,
            hybrid_policy,
            config,
        ) = self._inputs()
        adapter = FakeAdapter(
            [
                {
                    "semantic_flags": expected_semantic_flags(
                        task,
                        hybrid_policy,
                    )
                }
                for task in tasks["tasks"]
            ]
        )
        records, summary = execute_tasks(
            adapter,
            tasks_doc=tasks,
            contracts_doc=contracts,
            prompts=prompts,
            output_schema=schema,
            base_policy=base_policy,
            hybrid_policy=hybrid_policy,
            config=config,
        )
        self.assertEqual(len(records), 55)
        self.assertEqual(summary["semantic_schema_valid_rate"], 1.0)
        self.assertEqual(summary["semantic_flags_exact_accuracy"], 1.0)
        self.assertEqual(summary["merged_flags_exact_accuracy"], 1.0)
        self.assertEqual(summary["action_accuracy"], 1.0)

    def test_execution_refuses_before_adapter_use_without_authorization(self):
        target = (
            "Tools.core_freeze.e2_contract_boundaries."
            "run_e2_hybrid_semantic_development.AUTHORIZATION_PATH"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.json"
            with patch(target, missing):
                with self.assertRaisesRegex(
                    FileNotFoundError,
                    "authorization is pending",
                ):
                    run_experiment(FakeAdapter([]))

    def test_opening_package_is_hash_bound_and_secret_free(self):
        report = load_json(OUTPUT_DIR / "candidate_report.json")
        manifest = load_json(OUTPUT_DIR / "artifact_manifest.json")
        self.assertEqual(report["status"], "prepared_not_authorized")
        self.assertEqual(manifest["external_api_calls"], 0)
        self.assertFalse(manifest["external_api_execution_authorized"])
        self.assertFalse(report["model_payload_audit"]["gold_labels_sent"])
        self.assertFalse(
            report["model_payload_audit"]["validation_dataset_sent"]
        )
        for artifact in manifest["artifacts"]:
            self.assertEqual(
                file_hash(OUTPUT_DIR / artifact["filename"]),
                artifact["sha256"],
            )
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in OUTPUT_DIR.iterdir()
            if path.is_file()
        )
        self.assertNotIn("sk-", combined)
        self.assertNotIn("DEEPSEEK_API_KEY=", combined)

    def test_opening_does_not_snapshot_validation_dataset(self):
        names = {path.name for path in OUTPUT_DIR.iterdir()}
        self.assertNotIn("e2_validation_tasks_v1.json", names)
        report = load_json(OUTPUT_DIR / "candidate_report.json")
        self.assertIn(
            "40-task independent E2 validation candidate",
            report["excluded_external_data_scope"],
        )

    def test_builder_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "opening"
            report = build_package(output)
            self.assertEqual(report["status"], "prepared_not_authorized")
            with self.assertRaises(FileExistsError):
                build_package(output)


if __name__ == "__main__":
    unittest.main()
