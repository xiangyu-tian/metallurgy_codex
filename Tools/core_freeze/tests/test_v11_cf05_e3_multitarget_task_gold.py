import copy
import json
import unittest

from Tools.core_freeze.e3_routing import revalidate_e3_multitarget_task_gold as revalidate


class V11Cf05E3MultitargetTaskGoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = revalidate.load_json(revalidate.CONFIG_PATH)
        task_path = revalidate.WORKSPACE / cls.config["bindings"]["development_taskset"]["path"]
        tasks = revalidate.load_json(task_path)["tasks"]
        cls.expected_by_input = {}
        for task in tasks:
            if task["source_tool_id"] not in cls.config["target_tool_ids"]:
                continue
            key = json.dumps(task["canonical_inputs"], sort_keys=True)
            checks = task["scoring_rule"]["checks"]
            cls.expected_by_input[key] = {row["path"]: row["value"] for row in checks}

        def fake_invoke(tool_id, params):
            expected = cls.expected_by_input[json.dumps(params, sort_keys=True)]
            if tool_id == "E3C001":
                result = {"value": expected["value"]}
            elif tool_id == "E3C002":
                result = {"elements": expected["elements"]}
            elif tool_id == "E3C005":
                result = {"normalized": expected["normalized"]}
            else:
                raise AssertionError(tool_id)
            return {"success": True, "result": result, "error_code": None, "error": None}

        cls.result = revalidate.build(
            cls.config,
            invoke_fn=fake_invoke,
            validate_runtime_environment=False,
        )

    def test_all_bound_inputs_are_immutable(self):
        for binding in self.config["bindings"].values():
            revalidate.validate_binding(binding)

    def test_candidate_scope_classification_is_complete(self):
        rows = {row["target_tool_id"]: row for row in self.result["screening_rows"]}
        self.assertEqual(rows["A001"]["scoped_neighbor_tool_ids"], ["E3C006"])
        self.assertEqual(
            set(rows["A002"]["scoped_neighbor_tool_ids"]),
            {"A003", "E3C002", "E3C008", "E3C009"},
        )
        self.assertEqual(
            set(rows["A004"]["scoped_neighbor_tool_ids"]),
            {"A003", "E3C005", "E3C012", "E3C013", "E3C014", "E3C015"},
        )
        self.assertEqual(
            set(rows["B019"]["scoped_neighbor_tool_ids"]),
            {"A005", "B025", "C009", "G013"},
        )
        self.assertTrue(all(row["classification_complete"] for row in rows.values()))

    def test_exact_33_non_a003_tasks_are_revalidated(self):
        report = self.result["report"]
        self.assertEqual(report["task_count"], 33)
        self.assertEqual(report["execution_count"], 25)
        self.assertTrue(report["all_direct_candidate_executions_succeeded"])
        self.assertEqual(
            {row["target_tool_id"]: row["task_count"] for row in report["target_summaries"]},
            {"A001": 10, "A002": 7, "A004": 8, "B019": 8},
        )

    def test_direct_alternatives_enter_only_when_frozen_checks_pass(self):
        for row in self.result["task_rows"]:
            target_id = row["target_tool_id"]
            expected = {
                "A001": ["A001", "E3C001"],
                "A002": ["A002", "E3C002"],
                "A004": ["A004", "E3C005"],
                "B019": ["B019"],
            }[target_id]
            self.assertEqual(row["revalidated_primary_acceptable_tools"], expected)

    def test_committed_real_run_records_expected_a004_boundary(self):
        output_dir = (
            revalidate.WORKSPACE
            / "outputs"
            / "v11_cf05_e3_multitarget_task_gold_candidate_v1_20260810"
        )
        report = json.loads(
            (output_dir / "multitarget_task_gold_report.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            report["observed_contract_inapplicable_task_ids"],
            ["E1B2-A004-007", "E1B2-A004-008"],
        )
        self.assertEqual(
            report["observed_contract_inapplicable_task_ids"],
            report["expected_contract_inapplicable_task_ids"],
        )
        self.assertTrue(report["all_execution_outcomes_match_policy"])
        self.assertTrue(report["development_mixed_realistic_opening_allowed"])

    def test_failed_numeric_check_rejects_direct_candidate(self):
        task = {
            "canonical_inputs": {"value": 1, "source_unit": "kg", "target_unit": "g"},
            "scoring_rule": {
                "checks": [
                    {"path": "value", "op": "approx", "value": 1000, "abs_tol": 0, "rel_tol": 0}
                ]
            },
        }
        result = revalidate.evaluate_candidate(
            task,
            "E3C001",
            {"value": "result.converted_value"},
            lambda _tool_id, _params: {"success": True, "result": {"converted_value": 999}},
        )
        self.assertFalse(result["directly_acceptable"])

    def test_scope_and_inference_escalations_are_rejected(self):
        for field in (
            "full_137_registry_gold_claim_allowed",
            "confirmatory_use_allowed",
            "external_api_calls_authorized",
            "core_frozen",
        ):
            invalid = copy.deepcopy(self.config)
            invalid[field] = True
            with self.assertRaisesRegex(ValueError, "must remain false"):
                revalidate.build(
                    invalid,
                    invoke_fn=lambda _tool_id, _params: {},
                    validate_runtime_environment=False,
                )


if __name__ == "__main__":
    unittest.main()
