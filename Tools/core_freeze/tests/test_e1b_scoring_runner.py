import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[2]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

E1B_DIR = TOOLS_DIR / "core_freeze" / "e1b_pilot"
if str(E1B_DIR) not in sys.path:
    sys.path.insert(0, str(E1B_DIR))

from models_core import ModelRegistry  # noqa: E402
from models_core.llm_adapters import LLMAdapterError  # noqa: E402
from core_freeze.e1b_pilot.e1b_scoring import (  # noqa: E402
    extract_json_answer,
    parse_and_score,
)
from run_e1b_pilot import (  # noqa: E402
    load_json,
    run_experiment,
    write_outputs,
)
from analyze_e1b_pilot import analyze_records, write_analysis  # noqa: E402


class FakeAdapter:
    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = []

    def complete(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        content = self.contents.pop(0)
        if isinstance(content, Exception):
            raise content
        return {
            "id": f"fake-{len(self.calls)}",
            "model": "deepseek-v4-flash",
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

    def configuration(self):
        return {
            "provider": "fake",
            "model": "deepseek-v4-flash",
            "api_key_configured": False,
        }


class E1bScoringTests(unittest.TestCase):
    def test_extracts_direct_fenced_and_single_embedded_objects(self):
        variants = [
            '{"value": 1000}',
            '```json\n{"value": 1000}\n```',
            '结果如下：{"value": 1000}',
        ]
        for text in variants:
            with self.subTest(text=text):
                result = extract_json_answer(text)
                self.assertEqual(result["status"], "parsed")
                self.assertEqual(result["answer"], {"value": 1000})

    def test_multiple_objects_are_ambiguous(self):
        result = extract_json_answer('{"value": 1}\n{"value": 2}')
        self.assertEqual(result["status"], "ambiguous")
        self.assertIsNone(result["answer"])

    def test_embedded_nested_object_is_one_answer_not_two(self):
        result = extract_json_answer(
            '结果如下：{"elements":{"Fe":2,"O":3}}。'
        )
        self.assertEqual(result["status"], "parsed")
        self.assertEqual(
            result["answer"],
            {"elements": {"Fe": 2, "O": 3}},
        )

    def test_approximate_and_structured_checks(self):
        scoring_rule = {
            "checks": [
                {
                    "path": "molar_mass",
                    "op": "approx",
                    "value": 159.687,
                    "abs_tol": 0.0001,
                },
                {
                    "path": "elements",
                    "op": "equal",
                    "value": {"Fe": 2.0, "O": 3.0},
                },
            ]
        }
        result = parse_and_score(
            '{"molar_mass":159.68705,"elements":{"Fe":2,"O":3}}',
            scoring_rule,
        )
        self.assertTrue(result["correct"])
        self.assertEqual(result["parse_status"], "parsed")
        self.assertIsNotNone(result["normalized_error"])

    def test_boolean_does_not_pass_numeric_check(self):
        result = parse_and_score(
            '{"value": true}',
            {
                "checks": [
                    {"path": "value", "op": "approx", "value": 1, "abs_tol": 0}
                ]
            },
        )
        self.assertFalse(result["correct"])

    def test_boolean_does_not_pass_nested_numeric_equality(self):
        result = parse_and_score(
            '{"elements":{"Fe":true,"O":3}}',
            {
                "checks": [
                    {
                        "path": "elements",
                        "op": "equal",
                        "value": {"Fe": 1.0, "O": 3.0},
                    }
                ]
            },
        )
        self.assertFalse(result["correct"])


class E1bRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks_path = (
            TOOLS_DIR.parent
            / "outputs"
            / "e1b_pilot_v1_20260730"
            / "e1b_tasks.json"
        )
        cls.config_path = E1B_DIR / "run_config_v1.json"
        cls.tasks_doc = load_json(cls.tasks_path)
        cls.run_config = load_json(cls.config_path)

    def test_offline_pair_runs_and_scores_without_tool_selection_loss(self):
        registry = ModelRegistry()
        registry.discover()
        adapter = FakeAdapter(['{"value":999}', '{"value":1000}'])
        records, summary = run_experiment(
            tasks_doc=self.tasks_doc,
            run_config=self.run_config,
            registry=registry,
            adapter=adapter,
            repeats=1,
            max_tasks=1,
        )
        self.assertEqual(len(records), 2)
        self.assertFalse(records[0]["correct"])
        self.assertTrue(records[1]["correct"])
        self.assertTrue(records[1]["tool_execution"]["success"])
        self.assertEqual(summary["descriptive_accuracy_gain"], 1.0)
        self.assertEqual(summary["paired_complete_count"], 1)
        self.assertFalse(summary["confirmatory_inference_allowed"])
        self.assertIn("验证工具结果", adapter.calls[1]["messages"][1]["content"])
        analysis = analyze_records(records)
        self.assertEqual(analysis["complete_pair_count"], 1)
        self.assertEqual(analysis["positive_gain_task_count"], 1)
        self.assertEqual(analysis["task_level_mean_accuracy_gain"], 1.0)

    def test_provider_failure_is_audited_and_not_used_as_accuracy_loss(self):
        registry = ModelRegistry()
        registry.discover()
        adapter = FakeAdapter(
            [LLMAdapterError("temporary network failure"), '{"value":1000}']
        )
        records, summary = run_experiment(
            tasks_doc=self.tasks_doc,
            run_config=self.run_config,
            registry=registry,
            adapter=adapter,
            repeats=1,
            max_tasks=1,
        )
        self.assertEqual(records[0]["status"], "provider_error")
        self.assertEqual(summary["paired_complete_count"], 0)
        self.assertIsNone(summary["descriptive_accuracy_gain"])

    def test_fixed_provider_retry_policy_is_audited(self):
        registry = ModelRegistry()
        registry.discover()
        adapter = FakeAdapter(
            [
                LLMAdapterError("temporary network failure"),
                '{"value":1000}',
                '{"value":1000}',
            ]
        )
        run_config = copy.deepcopy(self.run_config)
        run_config["provider_max_attempts"] = 2
        run_config["retry_backoff_seconds"] = 0
        records, summary = run_experiment(
            tasks_doc=self.tasks_doc,
            run_config=run_config,
            registry=registry,
            adapter=adapter,
            repeats=1,
            max_tasks=1,
        )
        self.assertEqual([row["status"] for row in records], ["completed"] * 2)
        self.assertEqual(records[0]["provider_attempt_count"], 2)
        self.assertEqual(records[1]["provider_attempt_count"], 1)
        self.assertEqual(records[0]["provider_attempts"][0]["status"], "provider_error")
        self.assertEqual(summary["provider_attempt_count"], 3)
        self.assertEqual(summary["retried_cell_count"], 1)

    def test_output_package_has_hashes_and_no_secrets(self):
        registry = ModelRegistry()
        registry.discover()
        adapter = FakeAdapter(['{"value":1000}', '{"value":1000}'])
        records, summary = run_experiment(
            tasks_doc=self.tasks_doc,
            run_config=self.run_config,
            registry=registry,
            adapter=adapter,
            repeats=1,
            max_tasks=1,
        )
        with tempfile.TemporaryDirectory(
            dir=TOOLS_DIR.parent / "outputs"
        ) as temp_dir:
            output_dir = Path(temp_dir) / "run"
            report = write_outputs(
                output_dir=output_dir,
                tasks_path=self.tasks_path,
                config_path=self.config_path,
                tasks_doc=self.tasks_doc,
                run_config=self.run_config,
                records=records,
                summary=summary,
                adapter_configuration=adapter.configuration(),
            )
            self.assertFalse(report["adapter_configuration"]["api_key_configured"])
            self.assertTrue((output_dir / "run_records.jsonl").exists())
            self.assertTrue((output_dir / "task_source_snapshot.json").exists())
            self.assertTrue((output_dir / "run_config_snapshot.json").exists())
            self.assertTrue((output_dir / "runner_source_snapshot.py").exists())
            self.assertTrue((output_dir / "scoring_source_snapshot.py").exists())
            first_record = json.loads(
                (output_dir / "run_records.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()[0]
            )
            self.assertEqual(first_record["run_id"], report["run_id"])
            self.assertIn("executed_at", first_record)
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(encoding="utf-8")
            )
            filenames = {row["filename"] for row in manifest["artifacts"]}
            self.assertEqual(
                filenames,
                {
                    "run_records.jsonl",
                    "run_report.json",
                    "task_source_snapshot.json",
                    "run_config_snapshot.json",
                    "runner_source_snapshot.py",
                    "scoring_source_snapshot.py",
                },
            )
            self.assertTrue(
                all(
                    not Path(row["filename"]).is_absolute()
                    for row in manifest["artifacts"]
                )
            )
            analysis_dir = Path(temp_dir) / "analysis"
            analysis_report = write_analysis(output_dir, analysis_dir)
            self.assertEqual(
                analysis_report["analyzer_source_sha256"],
                next(
                    row["sha256"]
                    for row in json.loads(
                        (analysis_dir / "artifact_manifest.json").read_text(
                            encoding="utf-8"
                        )
                    )["artifacts"]
                    if row["filename"] == "analyzer_source_snapshot.py"
                ),
            )
            self.assertTrue(
                (analysis_dir / "analyzer_source_snapshot.py").is_file()
            )


if __name__ == "__main__":
    unittest.main()
