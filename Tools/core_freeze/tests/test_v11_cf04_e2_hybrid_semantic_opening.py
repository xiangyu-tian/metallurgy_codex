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
from Tools.core_freeze.e2_contract_boundaries.analyze_e2_hybrid_semantic_development import (
    compute_gate_metrics,
    evaluate_gate,
)
from Tools.core_freeze.e2_contract_boundaries.run_e2_development import (
    file_hash,
    load_json,
)
from Tools.core_freeze.e2_contract_boundaries.run_e2_hybrid_semantic_development import (
    BASE_POLICY_PATH,
    ADVANCEMENT_GATE_PATH,
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
    / "v11_cf04_e2_hybrid_semantic_dev_opening_v1_3_20260731"
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
        self.assertEqual(
            values["config"]["advancement_gate_sha256"],
            file_hash(ADVANCEMENT_GATE_PATH),
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

    def test_semantic_prompt_separates_structural_and_domain_evidence(self):
        prompts = load_json(PROMPTS_PATH)
        system = prompts["system"]
        self.assertIn(
            "结构型flags与语义型flags相互独立且可以同时成立",
            system,
        )
        self.assertIn(
            "不得从参数字段数量或组成标量数量推断组元数或相数",
            system,
        )
        self.assertIn(
            "字段缺失本身不提供该字段的语义越界证据",
            system,
        )
        self.assertIn(
            "显式歧义候选若全部违反同一契约边界",
            system,
        )
        self.assertIn(
            "服务不可用或版本错配不得停止语义判断",
            system,
        )
        self.assertIn(
            "只有request_context中的requested_system、requested_phase_count或requested_component_count",
            system,
        )
        self.assertIn(
            "参数值、单位对、语法、元素集、组成范围或verification_scope违反仍是contract_defined_out_of_domain",
            system,
        )

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
        self.assertEqual(summary["structural_flags_exact_count"], 55)
        self.assertEqual(summary["merged_flags_exact_count"], 55)
        self.assertEqual(summary["action_correct_count"], 55)
        self.assertEqual(summary["premature_call_count"], 0)

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
        self.assertEqual(
            report["advancement_gate"]["required_check_count"],
            11,
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
        self.assertIn("advancement_gate_snapshot.json", names)
        self.assertIn("analyzer_snapshot.py", names)
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

    def test_perfect_offline_records_pass_frozen_advancement_gate(self):
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
        records, _summary = execute_tasks(
            adapter,
            tasks_doc=tasks,
            contracts_doc=contracts,
            prompts=prompts,
            output_schema=schema,
            base_policy=base_policy,
            hybrid_policy=hybrid_policy,
            config=config,
        )
        metrics = compute_gate_metrics(
            records,
            {"validation_dataset_access": "forbidden"},
        )
        evaluation = evaluate_gate(
            metrics,
            load_json(ADVANCEMENT_GATE_PATH),
        )
        self.assertTrue(evaluation["all_required_checks_passed"])
        self.assertEqual(
            evaluation["decision"],
            "advance_to_validation_preparation",
        )
        self.assertFalse(evaluation["validation_dataset_may_be_opened"])

    def test_failed_gate_requires_development_revision(self):
        gate = load_json(ADVANCEMENT_GATE_PATH)
        metrics = {
            rule["metric"]: rule["threshold"]
            for rule in gate["required_checks"]
        }
        metrics["semantic_supported_flag_macro_f1"] = 0.5
        evaluation = evaluate_gate(metrics, gate)
        self.assertFalse(evaluation["all_required_checks_passed"])
        self.assertEqual(
            evaluation["decision"],
            "revise_on_development_only",
        )
        self.assertFalse(evaluation["validation_dataset_may_be_opened"])

    def test_missing_gate_metric_fails_closed(self):
        evaluation = evaluate_gate(
            {},
            load_json(ADVANCEMENT_GATE_PATH),
        )
        self.assertFalse(evaluation["all_required_checks_passed"])
        self.assertEqual(evaluation["passed_check_count"], 0)


if __name__ == "__main__":
    unittest.main()
