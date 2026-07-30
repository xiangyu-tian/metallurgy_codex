import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = TOOLS_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from core_freeze.e1b_v2.apply_candidate_gate_policy import (  # noqa: E402
    audit_policy,
    classify_task,
    file_hash,
    load_json,
    validate_policy,
)


class E1bCandidateGatePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v2_dir = TOOLS_DIR / "core_freeze" / "e1b_v2"
        cls.policy_path = cls.v2_dir / "candidate_gate_policy_v1.json"
        cls.policy = load_json(cls.policy_path)
        cls.tasks_path = (
            PROJECT_ROOT
            / "outputs"
            / "e1b_benefit_taskset_v2_20260730"
            / "e1b_benefit_tasks_v2.json"
        )
        cls.analysis_dir = (
            PROJECT_ROOT
            / "outputs"
            / "e1b_v2_benefit_analysis_r3_20260730"
        )
        cls.tasks = load_json(cls.tasks_path)["tasks"]

    def test_policy_contract_is_pre_gate_and_uses_allowed_features_only(self):
        validate_policy(self.policy)
        self.assertEqual(
            self.policy["policy_status"],
            "candidate_frozen_pre_gate",
        )
        self.assertFalse(
            self.policy["development_evidence"][
                "gate_evaluation_effects_observed"
            ]
        )
        self.assertTrue(
            self.policy["freeze_constraints"][
                "gate_evaluation_may_not_modify_this_version"
            ]
        )
        self.assertIn(
            "task_id",
            self.policy["feature_contract"]["forbidden_features"],
        )

    def test_strict_versioned_calls_and_approximate_variant_does_not(self):
        strict = next(
            task
            for task in self.tasks
            if task["source_tool_id"] == "A003"
            and task["precision_policy"] == "strict_versioned"
        )
        approximate = next(
            task
            for task in self.tasks
            if task["base_task_group_id"] == strict["base_task_group_id"]
            and task["precision_policy"] == "approximate_educational"
        )
        strict_decision = classify_task(strict, self.policy)
        approximate_decision = classify_task(approximate, self.policy)
        self.assertEqual(strict_decision["action"], "CALL_VERIFIED_TOOL")
        self.assertEqual(
            strict_decision["rule_id"],
            "CGP-V1-STRICT-VERSIONED",
        )
        self.assertEqual(approximate_decision["action"], "ANSWER_WITHOUT_TOOL")

    def test_decision_ignores_task_id_problem_text_and_formula(self):
        task = next(
            row
            for row in self.tasks
            if row["precision_policy"] == "strict_versioned"
        )
        mutated = copy.deepcopy(task)
        mutated["task_id"] = "UNSEEN-TASK"
        mutated["base_task_group_id"] = "UNSEEN-GROUP"
        mutated["problem_text"] = "completely replaced"
        mutated["canonical_inputs"]["formula"] = "UNSEEN"
        self.assertEqual(
            classify_task(task, self.policy),
            classify_task(mutated, self.policy),
        )

    def test_conditioned_normalization_rule_is_generic(self):
        rescaling = {
            "source_tool_id": "A004",
            "precision_policy": "six_decimal_components",
            "canonical_inputs": {
                "compositions": {"bulk": 999.0, "trace": 1.0}
            },
        }
        already_normalized = copy.deepcopy(rescaling)
        already_normalized["canonical_inputs"]["compositions"] = {
            "bulk": 0.999,
            "trace": 0.001,
        }
        rescaling_decision = classify_task(rescaling, self.policy)
        normalized_decision = classify_task(already_normalized, self.policy)
        self.assertEqual(rescaling_decision["action"], "CALL_VERIFIED_TOOL")
        self.assertEqual(
            rescaling_decision["rule_id"],
            "CGP-V1-CONDITIONED-NORMALIZATION",
        )
        self.assertEqual(normalized_decision["action"], "ANSWER_WITHOUT_TOOL")

    def test_policy_rejects_forbidden_decision_field(self):
        contaminated = copy.deepcopy(self.policy)
        contaminated["rules"][0]["when"]["all"][0]["field"] = "task_id"
        with self.assertRaisesRegex(ValueError, "forbidden"):
            validate_policy(contaminated)

    def test_development_fit_audit_is_deterministic_and_nonconfirmatory(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            reports = []
            manifests = []
            for temp_dir in (first, second):
                output_dir = Path(temp_dir)
                report = audit_policy(
                    self.policy_path,
                    self.tasks_path,
                    self.analysis_dir / "benefit_analysis_report.json",
                    self.analysis_dir / "task_effects.csv",
                    output_dir,
                )
                reports.append(report)
                manifests.append(
                    json.loads(
                        (output_dir / "artifact_manifest.json").read_text(
                            encoding="utf-8"
                        )
                    )
                )
                for row in manifests[-1]["artifacts"]:
                    self.assertEqual(
                        file_hash(output_dir / row["filename"]),
                        row["sha256"],
                    )
            self.assertEqual(reports[0], reports[1])
            self.assertEqual(manifests[0], manifests[1])
            report = reports[0]
            self.assertEqual(report["task_count"], 45)
            self.assertEqual(report["repeat_cell_count"], 135)
            self.assertEqual(report["call_cell_count"], 21)
            self.assertAlmostEqual(report["call_rate"], 21 / 135)
            self.assertAlmostEqual(
                report["candidate_policy_accuracy"],
                134 / 135,
            )
            self.assertAlmostEqual(
                report["captured_positive_gain_fraction"],
                17 / 18,
            )
            self.assertFalse(
                report["interpretation"]["confirmatory_inference_allowed"]
            )
            self.assertFalse(
                report["interpretation"]["gate_evaluation_opened"]
            )


if __name__ == "__main__":
    unittest.main()
