import json
import unittest
from pathlib import Path

from Tools.core_freeze.e2_contract_boundaries.analyze_e2_v1_1_recheck import (
    BASELINE_DIR,
    build_comparison,
    file_hash,
    load_json,
    load_jsonl,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
RUN_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_policy_v1_1_recheck_20260731"
)
ANALYSIS_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_policy_v1_1_recheck_analysis_20260731"
)


class V11Cf04E2V11RecheckAnalysisTests(unittest.TestCase):
    def test_successful_run_is_complete_hash_bound_and_secret_free(self):
        report = load_json(RUN_DIR / "run_report.json")
        self.assertEqual(report["summary"]["completed_count"], 55)
        self.assertEqual(report["summary"]["provider_failure_count"], 0)
        self.assertEqual(report["summary"]["schema_valid_rate"], 1.0)
        self.assertEqual(
            report["summary"]["model_output_fields"],
            ["flags"],
        )
        manifest = load_json(RUN_DIR / "artifact_manifest.json")
        for artifact in manifest["artifacts"]:
            self.assertEqual(
                file_hash(RUN_DIR / artifact["filename"]),
                artifact["sha256"],
            )
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in RUN_DIR.iterdir()
            if path.is_file()
        )
        self.assertNotIn("sk-", combined)

    def test_paired_comparison_preserves_improvements_and_regressions(self):
        outputs = build_comparison(
            current_records=load_jsonl(RUN_DIR / "run_records.jsonl"),
            current_report=load_json(RUN_DIR / "run_report.json"),
            baseline_records=load_jsonl(
                BASELINE_DIR / "counterfactual_replay_records.jsonl"
            ),
            baseline_report=load_json(
                BASELINE_DIR / "counterfactual_replay_report.json"
            ),
        )
        errors, _, flags, report = outputs
        self.assertEqual(len(errors), 7)
        self.assertEqual(
            report["paired_flags_transitions"],
            {
                "correct_to_correct": 40,
                "correct_to_incorrect": 2,
                "incorrect_to_correct": 8,
                "incorrect_to_incorrect": 5,
            },
        )
        self.assertGreater(
            report["metrics"]["flags_exact_accuracy"]["change"],
            0,
        )
        self.assertLess(
            report["metrics"]["action_accuracy"]["change"],
            0,
        )
        self.assertFalse(
            report["development_gate"][
                "clarify_action_accuracy_improved"
            ]
        )
        unsupported = next(
            row
            for row in flags
            if row["flag"] == "contract_defined_unsupported_system"
        )
        self.assertEqual(unsupported["v1_1_recall"], 1.0)

    def test_analysis_manifest_binds_all_outputs(self):
        manifest = load_json(ANALYSIS_DIR / "artifact_manifest.json")
        for artifact in manifest["artifacts"]:
            self.assertEqual(
                file_hash(ANALYSIS_DIR / artifact["filename"]),
                artifact["sha256"],
            )
        report = load_json(ANALYSIS_DIR / "comparison_report.json")
        self.assertFalse(
            report["interpretation"]["confirmatory_inference_allowed"]
        )
        self.assertFalse(report["interpretation"]["core_frozen"])


if __name__ == "__main__":
    unittest.main()
