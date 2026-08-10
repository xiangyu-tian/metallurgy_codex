import copy
import csv
import json
import unittest
from pathlib import Path

from Tools.core_freeze.e3_routing import audit_e3_multitarget_readiness as audit


class V11Cf05E3MultitargetReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = audit.load_json(audit.CONFIG_PATH)
        cls.result = audit.build(cls.config)
        cls.rows = {
            row["target_tool_id"]: row
            for row in cls.result["readiness_matrix"]["rows"]
        }

    def test_all_bound_inputs_are_immutable(self):
        for binding in self.config["bindings"].values():
            audit.validate_binding(binding)

    def test_all_targets_have_tasks_and_independent_references(self):
        self.assertEqual(self.result["report"]["task_count"], 45)
        self.assertEqual(self.result["report"]["task_source_ready_target_count"], 5)
        self.assertEqual(
            {target_id: row["task_count"] for target_id, row in self.rows.items()},
            {"A001": 10, "A002": 7, "A003": 12, "A004": 8, "B019": 8},
        )

    def test_task_availability_is_not_misreported_as_gold_readiness(self):
        self.assertTrue(all(row["task_source_and_independent_reference_ready"] for row in self.rows.values()))
        self.assertTrue(self.rows["A003"]["expanded_registry_task_gold_revalidated"])
        for target_id in ("A001", "A002", "A004", "B019"):
            self.assertFalse(self.rows[target_id]["expanded_registry_task_gold_revalidated"])
            self.assertFalse(self.rows[target_id]["mixed_realistic_opening_ready"])
        self.assertEqual(
            self.result["report"]["non_a003_task_count_requiring_expanded_registry_gold_revalidation"],
            33,
        )

    def test_only_a003_is_paired_4_and_paired_8_ready(self):
        self.assertEqual(self.result["report"]["paired_4_ready_target_ids"], ["A003"])
        self.assertEqual(self.result["report"]["paired_8_ready_target_ids"], ["A003"])
        self.assertTrue(self.rows["A003"]["controlled_dose_opening_ready"])
        self.assertFalse(any(
            self.rows[target_id]["controlled_dose_opening_ready"]
            for target_id in ("A001", "A002", "A004", "B019")
        ))

    def test_expansion_queue_is_deterministic_and_does_not_fill_slots(self):
        queue = self.result["expansion_queue"]
        self.assertEqual(
            [row["target_tool_id"] for row in queue["rows"]],
            ["A004", "B019", "A002", "A001"],
        )
        self.assertEqual(
            [row["missing_slots_to_paired_4"] for row in queue["rows"]],
            [2, 4, 4, 7],
        )
        self.assertFalse(queue["weak_neighbor_fill_allowed"])
        self.assertFalse(queue["formal_pool_generation_allowed"])

    def test_policy_escalations_are_rejected(self):
        for field in (
            "confirmatory_use_allowed",
            "external_api_calls_authorized",
            "core_frozen",
        ):
            invalid = copy.deepcopy(self.config)
            invalid[field] = True
            with self.assertRaisesRegex(ValueError, "must remain false"):
                audit.build(invalid)

    def test_committed_output_has_csv_and_complete_manifest(self):
        output_dir = (
            audit.WORKSPACE
            / "outputs"
            / "v11_cf05_e3_multitarget_readiness_v1_20260810"
        )
        report = json.loads(
            (output_dir / "multitarget_readiness_report.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(report, self.result["report"])
        with (output_dir / "target_readiness_matrix.csv").open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 5)
        manifest = json.loads(
            (output_dir / "artifact_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["artifact_count"], 6)
        for row in manifest["artifacts"]:
            path = output_dir / row["filename"]
            self.assertTrue(path.is_file())
            self.assertEqual(audit.sha256_file(path), row["sha256"])


if __name__ == "__main__":
    unittest.main()
