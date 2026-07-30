import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[2]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from core_freeze.e1b_v2.generate_e1b_v2 import (  # noqa: E402
    build_tasks,
    file_hash,
    generate,
    load_json,
    structural_errors,
)
from core_freeze.e1b_v2.validate_e1b_v2 import validate_package  # noqa: E402


class E1bV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core_dir = TOOLS_DIR / "core_freeze"
        cls.v2_dir = cls.core_dir / "e1b_v2"
        cls.seeds_path = cls.v2_dir / "task_seeds_v2.json"
        cls.contracts_path = (
            cls.core_dir / "verified_core" / "contracts_v1.json"
        )
        cls.seeds = load_json(cls.seeds_path)
        cls.contracts = load_json(cls.contracts_path)
        cls.tasks = build_tasks(cls.seeds, cls.contracts)

    def test_expected_counts_and_split_isolation(self):
        self.assertEqual(len(self.tasks), 72)
        self.assertEqual(
            Counter(task["source_tool_id"] for task in self.tasks),
            Counter(
                {
                    "A001": 16,
                    "A002": 12,
                    "A003": 20,
                    "A004": 12,
                    "B019": 12,
                }
            ),
        )
        self.assertEqual(
            Counter(task["split"] for task in self.tasks),
            Counter({"benefit_estimation": 45, "gate_evaluation": 27}),
        )
        group_splits = {}
        for task in self.tasks:
            group_splits.setdefault(task["base_task_group_id"], set()).add(
                task["split"]
            )
        self.assertTrue(all(len(splits) == 1 for splits in group_splits.values()))
        self.assertEqual(structural_errors(self.tasks, self.contracts), [])

    def test_a003_precision_variants_are_grouped_and_explicit(self):
        groups = {}
        for task in self.tasks:
            if task["source_tool_id"] == "A003":
                groups.setdefault(task["base_task_group_id"], []).append(task)
        self.assertEqual(len(groups), 10)
        for rows in groups.values():
            self.assertEqual(len(rows), 2)
            self.assertEqual(
                {row["precision_policy"] for row in rows},
                {"strict_versioned", "approximate_educational"},
            )
            self.assertEqual(len({row["split"] for row in rows}), 1)
            tolerances = {
                row["precision_policy"]: row["scoring_rule"]["checks"][0][
                    "abs_tol"
                ]
                for row in rows
            }
            self.assertEqual(tolerances["strict_versioned"], 0.0001)
            self.assertEqual(tolerances["approximate_educational"], 0.1)
            self.assertTrue(
                all("冻结原子量" in row["problem_text"] for row in rows)
            )

    def test_reference_generation_declares_no_production_import(self):
        self.assertTrue(
            all(
                task["reference_execution"]["production_code_imported"] is False
                for task in self.tasks
            )
        )
        self.assertTrue(
            all(
                task["canonical_inputs"] == task["expected_parameters"]
                for task in self.tasks
            )
        )

    def test_production_tools_match_all_independent_references(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            generate(self.seeds_path, self.contracts_path, output_dir)
            report = validate_package(
                output_dir / "e1b_tasks_v2.json",
                self.seeds_path,
                self.contracts_path,
                output_dir,
            )
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["production_execution_success_count"], 72)
            self.assertEqual(report["production_reference_match_count"], 72)
            self.assertEqual(report["group_split_leakage_count"], 0)
            manifest = load_json(output_dir / "artifact_manifest.json")
            self.assertEqual(manifest["validation_status"], "passed")
            self.assertTrue(
                all(
                    not Path(row["filename"]).is_absolute()
                    for row in manifest["artifacts"]
                )
            )

    def test_generation_and_validation_are_deterministic(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            hashes = []
            for temp_dir in (first, second):
                output_dir = Path(temp_dir)
                generate(self.seeds_path, self.contracts_path, output_dir)
                validate_package(
                    output_dir / "e1b_tasks_v2.json",
                    self.seeds_path,
                    self.contracts_path,
                    output_dir,
                )
                hashes.append(
                    {
                        name: file_hash(output_dir / name)
                        for name in (
                            "e1b_tasks_v2.json",
                            "generation_report.json",
                            "validation_report.json",
                            "artifact_manifest.json",
                        )
                    }
                )
            self.assertEqual(hashes[0], hashes[1])

    def test_document_status_never_claims_frozen_or_executed_api_runs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            generate(self.seeds_path, self.contracts_path, output_dir)
            validate_package(
                output_dir / "e1b_tasks_v2.json",
                self.seeds_path,
                self.contracts_path,
                output_dir,
            )
            tasks_doc = json.loads(
                (output_dir / "e1b_tasks_v2.json").read_text(encoding="utf-8")
            )
            report = json.loads(
                (output_dir / "validation_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(tasks_doc["dataset_status"], "prepared")
            self.assertFalse(tasks_doc["core_frozen"])
            self.assertFalse(report["api_model_runs_performed"])
            self.assertFalse(report["core_frozen"])


if __name__ == "__main__":
    unittest.main()
