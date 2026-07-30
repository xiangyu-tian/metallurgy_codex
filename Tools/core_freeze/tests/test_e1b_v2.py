import json
import copy
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
from core_freeze.e1b_v2.prepare_e1b_v2_smoke import (  # noqa: E402
    prepare_smoke_subset,
)
from core_freeze.e1b_v2.prepare_e1b_v2_benefit import (  # noqa: E402
    prepare_benefit_subset,
)
from core_freeze.e1b_v2.analyze_e1b_v2_benefit import (  # noqa: E402
    cluster_bootstrap,
)

E1B_PILOT_DIR = TOOLS_DIR / "core_freeze" / "e1b_pilot"
if str(E1B_PILOT_DIR) not in sys.path:
    sys.path.insert(0, str(E1B_PILOT_DIR))

from core_freeze.e1b_pilot.run_e1b_pilot import (  # noqa: E402
    run_experiment,
    validate_run_scope,
)
from models_core import ModelRegistry  # noqa: E402


class _SmokeFakeAdapter:
    def __init__(self, content):
        self.content = content

    def complete(self, messages, **kwargs):
        return {
            "id": "smoke-fake",
            "model": "deepseek-v4-flash",
            "message": {"role": "assistant", "content": self.content},
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }


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

    def test_smoke_subset_is_frozen_to_benefit_estimation(self):
        source_tasks_path = (
            TOOLS_DIR.parent
            / "outputs"
            / "e1b_taskset_v2_20260730"
            / "e1b_tasks_v2.json"
        )
        selection_path = self.v2_dir / "smoke_selection_v2.json"
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            report = prepare_smoke_subset(
                source_tasks_path,
                selection_path,
                output_dir,
            )
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["task_count"], 7)
            self.assertEqual(report["condition_run_cells_at_one_repeat"], 14)
            self.assertEqual(report["selected_splits"], ["benefit_estimation"])
            self.assertEqual(report["gate_evaluation_task_count"], 0)
            tasks_doc = load_json(output_dir / "e1b_smoke_tasks_v2.json")
            self.assertEqual(
                {task["source_tool_id"] for task in tasks_doc["tasks"]},
                {"A001", "A002", "A003", "A004", "B019"},
            )
            self.assertFalse(tasks_doc["gate_evaluation_opened"])

    def test_v2_smoke_scope_runs_offline_and_rejects_gate_tasks(self):
        source_tasks_path = (
            TOOLS_DIR.parent
            / "outputs"
            / "e1b_taskset_v2_20260730"
            / "e1b_tasks_v2.json"
        )
        selection_path = self.v2_dir / "smoke_selection_v2.json"
        run_config = load_json(self.v2_dir / "run_config_smoke_v2.json")
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            prepare_smoke_subset(
                source_tasks_path,
                selection_path,
                output_dir,
            )
            smoke_doc = load_json(output_dir / "e1b_smoke_tasks_v2.json")
            registry = ModelRegistry()
            registry.discover()
            adapter = _SmokeFakeAdapter('{"value":50662.5}')
            records, summary = run_experiment(
                tasks_doc=smoke_doc,
                run_config=run_config,
                registry=registry,
                adapter=adapter,
                repeats=1,
                max_tasks=1,
            )
            self.assertEqual(len(records), 2)
            self.assertEqual(summary["paired_complete_count"], 1)
            self.assertTrue(all(row["split"] == "benefit_estimation" for row in records))
            self.assertTrue(all(row["base_task_group_id"] for row in records))
            self.assertTrue(all(row["precision_policy"] for row in records))

            contaminated = copy.deepcopy(smoke_doc)
            full_doc = load_json(source_tasks_path)
            gate_task = next(
                task
                for task in full_doc["tasks"]
                if task["split"] == "gate_evaluation"
            )
            contaminated["tasks"].append(gate_task)
            contaminated["task_count"] += 1
            with self.assertRaisesRegex(ValueError, "selected_split|sealed"):
                validate_run_scope(contaminated, run_config)

    def test_complete_benefit_snapshot_contains_only_45_front_tasks(self):
        source_tasks_path = (
            TOOLS_DIR.parent
            / "outputs"
            / "e1b_taskset_v2_20260730"
            / "e1b_tasks_v2.json"
        )
        run_config = load_json(self.v2_dir / "run_config_benefit_v2.json")
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            report = prepare_benefit_subset(source_tasks_path, output_dir)
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["task_count"], 45)
            self.assertEqual(report["condition_run_cells_at_three_repeats"], 270)
            self.assertEqual(report["selected_splits"], ["benefit_estimation"])
            self.assertEqual(report["gate_evaluation_task_count"], 0)
            benefit_doc = load_json(output_dir / "e1b_benefit_tasks_v2.json")
            validate_run_scope(benefit_doc, run_config)
            self.assertEqual(
                Counter(task["source_tool_id"] for task in benefit_doc["tasks"]),
                Counter(
                    {
                        "A001": 10,
                        "A002": 7,
                        "A003": 12,
                        "A004": 8,
                        "B019": 8,
                    }
                ),
            )
            self.assertTrue(
                all(
                    task["split"] == "benefit_estimation"
                    for task in benefit_doc["tasks"]
                )
            )

    def test_group_cluster_bootstrap_is_deterministic(self):
        groups = {
            "G1": [1.0, 1.0],
            "G2": [0.0],
            "G3": [0.0, 0.0, 0.0],
        }
        first = cluster_bootstrap(groups, seed=7, iterations=1000)
        second = cluster_bootstrap(groups, seed=7, iterations=1000)
        self.assertEqual(first, second)
        self.assertEqual(first["cluster_unit"], "base_task_group_id")
        self.assertAlmostEqual(first["task_weighted"]["estimate"], 2 / 6)
        self.assertAlmostEqual(first["group_equal"]["estimate"], 1 / 3)
        self.assertFalse(first["confirmatory_inference_allowed"])


if __name__ == "__main__":
    unittest.main()
