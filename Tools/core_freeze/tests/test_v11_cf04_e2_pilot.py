import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.e2_contract_boundaries.build_e2_pilot import (
    PROJECT_ROOT,
    build_dataset,
    derive_policy,
    file_hash,
    load_json,
    POLICY_PATH,
    run_build,
    validate_dataset,
)


class V11Cf04E2PilotTests(unittest.TestCase):
    def test_dataset_is_deterministic_and_rule_derived(self):
        tasks_a, events_a = build_dataset()
        tasks_b, events_b = build_dataset()
        self.assertEqual(tasks_a, tasks_b)
        self.assertEqual(events_a, events_b)
        self.assertEqual(len(tasks_a), 55)
        self.assertEqual(
            sum(len(task["expected_flags"]) >= 2 for task in tasks_a),
            15,
        )
        self.assertTrue(
            all(
                task["confirmatory_inference_allowed"] is False
                for task in tasks_a
            )
        )

    def test_priority_prefers_clarification_over_unavailability(self):
        policy = load_json(POLICY_PATH)
        result = derive_policy(
            ["missing_parameter", "unavailable"],
            policy,
        )
        self.assertEqual(
            result["primary_status"], "missing_or_ambiguous_input"
        )
        self.assertEqual(result["allowed_actions"], ["clarify"])
        self.assertEqual(result["policy_expected_action"], "clarify")

    def test_core_categories_cover_all_five_tools(self):
        tasks, events = build_dataset()
        audit = validate_dataset(tasks, events)
        self.assertEqual(audit["candidate_evidence_status"], "passed")
        self.assertEqual(audit["status"], "in_progress")
        self.assertEqual(audit["summary"]["tool_count"], 5)
        self.assertEqual(audit["summary"]["ready_task_count"], 5)
        self.assertEqual(audit["summary"]["mutated_task_count"], 50)
        self.assertEqual(audit["summary"]["multi_label_task_count"], 15)
        self.assertEqual(
            set(audit["summary"]["action_counts"]),
            {"call", "clarify", "refuse"},
        )

    def test_unavailable_contract_dimensions_remain_explicit_gaps(self):
        tasks, events = build_dataset()
        audit = validate_dataset(tasks, events)
        gap_types = {
            row["mutation_type"] for row in audit["coverage_gaps"]
        }
        self.assertEqual(
            gap_types,
            {
                "out_of_temperature_range",
                "out_of_pressure_range",
                "model_card_defined_ood",
            },
        )
        self.assertFalse(audit["confirmatory_inference_allowed"])
        self.assertFalse(audit["core_frozen"])

    def test_output_manifest_binds_artifacts_and_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "cf04"
            report = run_build(output_dir)
            self.assertEqual(report["candidate_evidence_status"], "passed")
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            for row in manifest["artifacts"]:
                artifact = output_dir / row["filename"]
                self.assertEqual(file_hash(artifact), row["sha256"])
            for row in manifest["source_artifacts"]:
                source = PROJECT_ROOT / row["filename"]
                self.assertEqual(file_hash(source), row["sha256"])

    def test_build_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "cf04"
            run_build(output_dir)
            with self.assertRaises(FileExistsError):
                run_build(output_dir)


if __name__ == "__main__":
    unittest.main()
