import csv
import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.analyze_v11_cf08_power import (
    PROJECT_ROOT,
    build_sample_size_options,
    file_hash,
    load_group_effects,
    repeat_stability,
    run_analysis,
)


class V11Cf08PowerTests(unittest.TestCase):
    def test_repeat_stability_supports_three_repeat_candidate(self):
        result = repeat_stability()
        self.assertEqual(result["pilot_repeat_count"], 3)
        self.assertEqual(result["task_count"], 45)
        self.assertEqual(result["stable_task_count"], 43)
        self.assertAlmostEqual(result["stable_task_fraction"], 43 / 45)
        self.assertAlmostEqual(result["repeat_gain_range"], 0.0)
        self.assertGreater(result["one_way_random_effects_icc"], 0.85)

    def test_sample_size_grid_uses_base_groups_not_repeat_cells(self):
        group_values = [
            row["accuracy_gain"] for row in load_group_effects()
        ]
        import statistics

        options = build_sample_size_options(statistics.stdev(group_values))
        self.assertEqual(len(options), 6)
        five_pp_80 = next(
            row
            for row in options
            if row["minimum_meaningful_accuracy_gain"] == 0.05
            and row["target_power"] == 0.80
        )
        self.assertEqual(
            five_pp_80["required_base_task_groups_uninflated"], 104
        )
        self.assertEqual(
            five_pp_80["recommended_base_task_groups"], 120
        )
        self.assertEqual(five_pp_80["planned_model_cells"], 1440)

    def test_candidate_is_ready_but_not_frozen(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "cf08"
            report = run_analysis(output_dir)
            self.assertEqual(report["status"], "in_progress")
            self.assertEqual(
                report["candidate_status"], "ready_for_review"
            )
            candidate = report["recommended_candidate"]
            self.assertEqual(candidate["approval_status"], "pending")
            self.assertEqual(candidate["base_task_groups"], 120)
            self.assertEqual(
                candidate["base_task_groups_per_verified_tool_family"], 24
            )
            self.assertEqual(candidate["model_run_repeats"], 3)
            self.assertFalse(candidate["formal_repeat_count_frozen"])
            self.assertFalse(candidate["formal_sample_size_frozen"])
            self.assertFalse(report["cf08_may_be_marked_passed"])
            self.assertFalse(report["core_frozen"])

            with (output_dir / "sample_size_options.csv").open(
                encoding="utf-8", newline=""
            ) as stream:
                options = list(csv.DictReader(stream))
            self.assertEqual(len(options), 6)

    def test_manifest_binds_outputs_and_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "cf08"
            run_analysis(output_dir)
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            for row in manifest["artifacts"]:
                artifact = output_dir / row["filename"]
                self.assertTrue(artifact.is_file())
                self.assertEqual(file_hash(artifact), row["sha256"])
            for row in manifest["source_artifacts"]:
                source = PROJECT_ROOT / row["filename"]
                self.assertTrue(source.is_file())
                self.assertEqual(file_hash(source), row["sha256"])

    def test_analysis_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "cf08"
            run_analysis(output_dir)
            with self.assertRaises(FileExistsError):
                run_analysis(output_dir)


if __name__ == "__main__":
    unittest.main()
