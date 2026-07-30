import json
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[2]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from core_freeze.e1b_pilot.generate_e1b_pilot import (  # noqa: E402
    build_tasks,
    generate,
    load_json,
    validate_tasks,
)


class E1bPilotGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core_dir = TOOLS_DIR / "core_freeze"
        cls.verified_dir = cls.core_dir / "verified_core"
        cls.e1b_dir = cls.core_dir / "e1b_pilot"
        cls.contracts = load_json(cls.verified_dir / "contracts_v1.json")
        cls.cases = load_json(cls.verified_dir / "reference_cases_v1.json")
        cls.templates = load_json(cls.e1b_dir / "templates_v1.json")

    def test_builds_expected_primary_task_pairs(self):
        tasks = build_tasks(self.contracts, self.cases, self.templates)
        self.assertEqual(len(tasks), 14)
        self.assertEqual(validate_tasks(tasks, self.contracts), [])
        self.assertEqual(
            {row["condition"] for row in tasks[0]["conditions"]},
            {"no_tool", "forced_verified_oracle_parameters"},
        )
        self.assertTrue(all(len(task["acceptable_tools"]) == 1 for task in tasks))

    def test_b019_tasks_never_use_auto_basis(self):
        tasks = build_tasks(self.contracts, self.cases, self.templates)
        b019_tasks = [task for task in tasks if task["source_tool_id"] == "B019"]
        self.assertTrue(b019_tasks)
        self.assertTrue(
            all(
                task["canonical_inputs"]["composition_basis"]
                in {"fraction", "percent"}
                for task in b019_tasks
            )
        )

    def test_a003_tasks_state_the_scored_precision(self):
        tasks = build_tasks(self.contracts, self.cases, self.templates)
        a003_tasks = [task for task in tasks if task["source_tool_id"] == "A003"]
        self.assertTrue(a003_tasks)
        self.assertTrue(
            all(
                "保留4位小数" in task["problem_text"]
                and "H=1.008" in task["problem_text"]
                and "Fe=55.845" in task["problem_text"]
                and "O=15.999" in task["problem_text"]
                for task in a003_tasks
            )
        )

    def test_generated_package_is_prepared_not_executed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = generate(
                self.verified_dir / "contracts_v1.json",
                self.verified_dir / "reference_cases_v1.json",
                self.e1b_dir / "templates_v1.json",
                Path(temp_dir),
            )
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["task_count"], 14)
            tasks_doc = json.loads(
                (Path(temp_dir) / "e1b_tasks.json").read_text(encoding="utf-8")
            )
            self.assertEqual(tasks_doc["dataset_status"], "prepared")
            self.assertFalse(tasks_doc["core_frozen"])
            manifest = json.loads(
                (Path(temp_dir) / "artifact_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(
                all(
                    not Path(row["filename"]).is_absolute()
                    for row in manifest["artifacts"]
                )
            )


if __name__ == "__main__":
    unittest.main()
