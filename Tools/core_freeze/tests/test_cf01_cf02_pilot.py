import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.prepare_cf01_cf02_pilot import (
    ANNOTATION_FIELDS,
    build_package,
)
from Tools.core_freeze.validate_cf01_cf02_pilot import (
    PilotValidationError,
    score_track_a,
    validate_constructed_track_b,
    validate_package,
    validate_track_a_prepared,
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


class PilotPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.package_dir = Path(self.temp_dir.name) / "pilot"
        build_package(self.package_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_prepared_package_passes_and_records_real_inventory_gap(self):
        report = validate_package(self.package_dir, "prepared")
        self.assertEqual(report["validation_status"], "passed")
        self.assertEqual(report["cf01_preparation"]["task_count"], 20)
        self.assertEqual(report["cf02_preparation"]["task_count"], 20)
        self.assertEqual(report["cf02_preparation"]["implemented_tool_count"], 17)
        self.assertEqual(report["cf02_preparation"]["tool_count_gap"], 103)
        self.assertEqual(report["cf02_preparation"]["pool_construction"], "blocked")

    def test_annotator_task_file_rejects_anticipated_label_leakage(self):
        path = self.package_dir / "track_a_tasks.json"
        payload = load(path)
        payload["tasks"][0]["anticipated_coverage"] = {
            "evidence_requirement": ["none"]
        }
        save(path, payload)
        with self.assertRaisesRegex(PilotValidationError, "leaks"):
            validate_track_a_prepared(self.package_dir)

    def test_annotator_task_file_rejects_semantic_source_hint(self):
        path = self.package_dir / "track_a_tasks.json"
        payload = load(path)
        payload["tasks"][0]["source_type"] = "authored_risk_pair"
        save(path, payload)
        with self.assertRaisesRegex(PilotValidationError, "leaks"):
            validate_track_a_prepared(self.package_dir)

    def test_not_started_annotation_rejects_prefilled_label(self):
        path = self.package_dir / "track_a_annotator_a.json"
        payload = load(path)
        payload["annotations"][0]["evidence_requirement"] = "none"
        save(path, payload)
        with self.assertRaisesRegex(PilotValidationError, "not-started annotation"):
            validate_track_a_prepared(self.package_dir)

    def test_completed_identical_annotations_pass_agreement_thresholds(self):
        for annotator_id in ("a", "b"):
            path = self.package_dir / f"track_a_annotator_{annotator_id}.json"
            payload = load(path)
            payload["independence_status"] = "completed"
            payload["annotator_name"] = f"reviewer-{annotator_id}"
            payload["annotator_role"] = "pilot_tester"
            payload["started_at"] = "2026-07-28T09:00:00+08:00"
            payload["completed_at"] = "2026-07-28T10:00:00+08:00"
            for index, row in enumerate(payload["annotations"]):
                for field in ANNOTATION_FIELDS:
                    row[field] = None
                row.update(
                    {
                        "evidence_requirement": (
                            "none" if index % 3 == 0 else
                            "optional" if index % 3 == 1 else
                            "required"
                        ),
                        "answerability": "answerable",
                        "information_status": "sufficient",
                        "capability_status": "available",
                        "risk_status": "normal",
                        "boundary_flags": [],
                        "allowed_actions": ["answer"],
                        "required_inputs": [],
                        "missing_inputs": [],
                        "coarse_capability": "test",
                        "action_reason": "synthetic agreement fixture",
                        "annotation_confidence": "high",
                        "disagreement_notes": None,
                    }
                )
            save(path, payload)
        report = score_track_a(self.package_dir)
        self.assertTrue(report["cf03_candidate_thresholds_passed"])
        self.assertEqual(report["disagreement_count"], 0)

    def test_completed_annotations_require_two_different_people(self):
        for annotator_id in ("a", "b"):
            path = self.package_dir / f"track_a_annotator_{annotator_id}.json"
            payload = load(path)
            payload["independence_status"] = "completed"
            payload["annotator_name"] = "same-reviewer"
            payload["annotator_role"] = "pilot_tester"
            payload["started_at"] = "2026-07-28T09:00:00+08:00"
            payload["completed_at"] = "2026-07-28T10:00:00+08:00"
            save(path, payload)
        with self.assertRaisesRegex(PilotValidationError, "different people"):
            score_track_a(self.package_dir)

    def test_constructed_stage_refuses_17_tool_snapshot(self):
        with self.assertRaisesRegex(PilotValidationError, "fewer than 120"):
            validate_constructed_track_b(self.package_dir)


if __name__ == "__main__":
    unittest.main()
