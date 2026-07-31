import copy
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = TOOLS_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from core_freeze.e1c_end_to_end.generate_e1c_tasks import (  # noqa: E402
    POLICY_SHA256,
    build_tasks,
    structural_errors,
)
from core_freeze.e1c_end_to_end.prepare_e1c_development import (  # noqa: E402
    prepare_development,
)
from core_freeze.e1c_end_to_end.run_e1c import (  # noqa: E402
    CONDITIONS,
    TOOL_IDS,
    run_cell,
    validate_run_scope,
)
from core_freeze.e1b_v2.apply_candidate_gate_policy import (  # noqa: E402
    load_json,
)
from models_core import ModelRegistry  # noqa: E402
from models_core.llm_adapters import model_tools  # noqa: E402


class _ScriptedAdapter:
    def __init__(self, messages):
        self.messages = list(messages)

    def complete(self, messages, **kwargs):
        if not self.messages:
            raise AssertionError("scripted adapter response queue exhausted")
        message = self.messages.pop(0)
        return {
            "id": "fake-e1c",
            "model": "deepseek-v4-flash",
            "message": message,
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        }


def _content(payload):
    return {
        "role": "assistant",
        "content": json.dumps(payload, ensure_ascii=False),
    }


def _tool_call(tool_id, parameters):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "fake-call",
                "type": "function",
                "function": {
                    "name": tool_id,
                    "arguments": json.dumps(parameters, ensure_ascii=False),
                },
            }
        ],
    }


class E1cEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e1c_dir = TOOLS_DIR / "core_freeze" / "e1c_end_to_end"
        cls.e1b_dir = TOOLS_DIR / "core_freeze" / "e1b_v2"
        cls.verified_dir = TOOLS_DIR / "core_freeze" / "verified_core"
        cls.output_dir = PROJECT_ROOT / "outputs" / "e1c_taskset_v1_20260731"
        cls.seeds = load_json(cls.e1c_dir / "task_seeds_v1.json")
        cls.contracts = load_json(cls.verified_dir / "contracts_v1.json")
        cls.policy = load_json(cls.e1b_dir / "candidate_gate_policy_v1.json")
        cls.tasks_doc = load_json(cls.output_dir / "e1c_tasks_v1.json")
        cls.prompts = load_json(cls.e1c_dir / "prompts_v1.json")
        cls.run_config = load_json(
            cls.e1c_dir / "run_config_development_v1.json"
        )
        cls.development_doc = load_json(
            PROJECT_ROOT
            / "outputs"
            / "e1c_development_v1_20260731"
            / "e1c_development_tasks_v1.json"
        )
        cls.registry = ModelRegistry()
        cls.registry.discover()
        cls.schemas = model_tools(cls.registry, TOOL_IDS)

    def test_taskset_is_new_balanced_and_evaluation_sealed(self):
        tasks = self.tasks_doc["tasks"]
        self.assertEqual(len(tasks), 60)
        self.assertEqual(
            Counter(task["source_tool_id"] for task in tasks),
            Counter(
                {"A001": 10, "A002": 10, "A003": 20, "A004": 12, "B019": 8}
            ),
        )
        self.assertEqual(
            Counter(task["split"] for task in tasks),
            Counter({"runner_development": 24, "end_to_end_evaluation": 36}),
        )
        self.assertFalse(self.tasks_doc["evaluation_split_opened"])
        self.assertTrue(
            all(
                task["frozen_policy_decision"]["policy_sha256"]
                == POLICY_SHA256
                for task in tasks
            )
        )
        e1b = load_json(
            PROJECT_ROOT
            / "outputs"
            / "e1b_taskset_v2_20260730"
            / "e1b_tasks_v2.json"
        )
        self.assertFalse(
            {
                task["base_task_group_id"] for task in tasks
            }
            & {
                task["base_task_group_id"] for task in e1b["tasks"]
            }
        )

    def test_independent_build_has_no_structural_errors(self):
        tasks = build_tasks(self.seeds, self.contracts, self.policy)
        e1b = load_json(
            PROJECT_ROOT
            / "outputs"
            / "e1b_taskset_v2_20260730"
            / "e1b_tasks_v2.json"
        )
        errors = structural_errors(
            tasks,
            self.contracts,
            {task["base_task_group_id"] for task in e1b["tasks"]},
        )
        self.assertEqual(errors, [])

    def test_production_validation_and_five_schemas_pass(self):
        report = load_json(self.output_dir / "validation_report.json")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["production_execution_success_count"], 60)
        self.assertEqual(report["production_reference_match_count"], 60)
        self.assertEqual(report["five_tool_schema_names"], TOOL_IDS)
        self.assertFalse(report["evaluation_split_opened"])

    def test_development_snapshot_excludes_all_evaluation_tasks(self):
        self.assertEqual(self.development_doc["task_count"], 24)
        self.assertEqual(
            {task["split"] for task in self.development_doc["tasks"]},
            {"runner_development"},
        )
        self.assertFalse(self.development_doc["evaluation_split_opened"])
        contaminated = copy.deepcopy(self.development_doc)
        contaminated["tasks"].append(
            next(
                task
                for task in self.tasks_doc["tasks"]
                if task["split"] == "end_to_end_evaluation"
            )
        )
        with self.assertRaisesRegex(ValueError, "outside selected split"):
            validate_run_scope(contaminated, self.prompts, self.run_config)

    def test_prepare_development_is_deterministic(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            reports = []
            for temp_dir in (first, second):
                reports.append(
                    prepare_development(
                        self.output_dir / "e1c_tasks_v1.json",
                        self.e1c_dir / "protocol_v1.md",
                        self.e1c_dir / "prompts_v1.json",
                        self.e1c_dir / "run_config_development_v1.json",
                        self.e1b_dir / "candidate_gate_policy_v1.json",
                        Path(temp_dir),
                    )
                )
            self.assertEqual(reports[0], reports[1])

    def _strict_task(self):
        return next(
            task
            for task in self.development_doc["tasks"]
            if task["source_tool_id"] == "A003"
            and task["precision_policy"] == "strict_versioned"
        )

    def test_all_six_conditions_run_offline_on_call_task(self):
        task = self._strict_task()
        expected_answer = {
            "molar_mass": task["scoring_rule"]["checks"][0]["value"]
        }
        scripts = {
            "no_tool": [_content(expected_answer)],
            "forced_verified_oracle_parameters": [_content(expected_answer)],
            "model_gate_oracle_parameters": [
                _content({"action": "CALL_VERIFIED_TOOL"}),
                _content(expected_answer),
            ],
            "oracle_gate_model_parameters": [
                _content(task["expected_parameters"]),
                _content(expected_answer),
            ],
            "direct_fc": [
                _tool_call(task["source_tool_id"], task["expected_parameters"]),
                _content(expected_answer),
            ],
            "boundary_guided_fc": [
                _tool_call(task["source_tool_id"], task["expected_parameters"]),
                _content(expected_answer),
            ],
        }
        records = []
        for condition in CONDITIONS:
            record = run_cell(
                task=task,
                condition=condition,
                repeat=1,
                registry=self.registry,
                adapter=_ScriptedAdapter(scripts[condition]),
                prompts=self.prompts,
                run_config=self.run_config,
                tool_schemas=self.schemas,
            )
            records.append(record)
            self.assertTrue(record["correct"], condition)
            self.assertEqual(record["primary_failure_stage"], "success", condition)
        by_condition = {row["condition"]: row for row in records}
        for condition in (
            "model_gate_oracle_parameters",
            "oracle_gate_model_parameters",
            "direct_fc",
            "boundary_guided_fc",
        ):
            self.assertTrue(by_condition[condition]["boundary_correct"])
        for condition in ("direct_fc", "boundary_guided_fc"):
            self.assertTrue(by_condition[condition]["tool_selection_correct"])
            self.assertTrue(by_condition[condition]["parameter_exact_match"])

    def test_overcall_is_attributed_before_correct_final_answer(self):
        task = next(
            row
            for row in self.development_doc["tasks"]
            if row["source_tool_id"] == "A003"
            and row["precision_policy"] == "approximate_educational"
        )
        expected_answer = {
            "molar_mass": task["scoring_rule"]["checks"][0]["value"]
        }
        record = run_cell(
            task=task,
            condition="direct_fc",
            repeat=1,
            registry=self.registry,
            adapter=_ScriptedAdapter(
                [
                    _tool_call(
                        task["source_tool_id"],
                        task["expected_parameters"],
                    ),
                    _content(expected_answer),
                ]
            ),
            prompts=self.prompts,
            run_config=self.run_config,
            tool_schemas=self.schemas,
        )
        self.assertTrue(record["correct"])
        self.assertFalse(record["boundary_correct"])
        self.assertEqual(
            record["primary_failure_stage"],
            "boundary_decision_error",
        )

    def test_invalid_gate_json_is_decision_parse_failure(self):
        task = self._strict_task()
        record = run_cell(
            task=task,
            condition="model_gate_oracle_parameters",
            repeat=1,
            registry=self.registry,
            adapter=_ScriptedAdapter(
                [{"role": "assistant", "content": "not-json"}]
            ),
            prompts=self.prompts,
            run_config=self.run_config,
            tool_schemas=self.schemas,
        )
        self.assertEqual(
            record["primary_failure_stage"],
            "decision_parse_failure",
        )


if __name__ == "__main__":
    unittest.main()
