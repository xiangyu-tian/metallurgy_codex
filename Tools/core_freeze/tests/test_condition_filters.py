"""Frozen H3/H4 filters and H4 Holm-family method comparisons."""

import unittest

from Tools.core_freeze.build_paired_contrasts import (
    build_h3_pairs,
    build_h4_method_contrasts,
    build_h4_scale_pairs,
    holm_adjust,
)
from Tools.core_freeze.run_h3_confirmatory import run_h3
from Tools.core_freeze.run_h4_confirmatory import run_h4
from Tools.core_freeze.tests.fixtures import document, h3_triplet, h4_pair, record


class ConditionFilterTests(unittest.TestCase):
    def test_h3_uses_only_controlled_120_count_8(self):
        valid = h3_triplet(
            functional_correct=False,
            lexical_correct=True,
            none_correct=True,
        )
        unrelated = [
            record(
                task_id="SIZE-50",
                tool_pool_size=50,
                pool_design="controlled_dose",
                near_neighbor_type="functional_overlap",
                near_neighbor_count=8,
                correct=True,
            ),
            record(
                task_id="MIXED",
                tool_pool_size=120,
                pool_design="mixed_realistic",
                near_neighbor_type="mixed",
                near_neighbor_count=8,
                correct=True,
            ),
        ]

        result = build_h3_pairs(valid + unrelated)

        self.assertEqual(len(result["direct_contrasts"]), 1)
        self.assertEqual(result["direct_contrasts"][0]["task_id"], "TASK-001")
        self.assertEqual(result["ignored_record_count"], 2)

    def test_h4_registers_exactly_three_hierarchical_comparisons(self):
        records = []
        records += h4_pair(
            method="hierarchical",
            correct_17=True,
            correct_120=True,
        )
        for baseline in ("full_schema", "lexical_top5", "dense_top5"):
            records += h4_pair(
                method=baseline,
                correct_17=True,
                correct_120=False,
            )
        records += h3_triplet(
            task_id="IGNORED-H3",
            functional_correct=False,
            lexical_correct=True,
            none_correct=True,
        )

        scale = build_h4_scale_pairs(records)
        planned = build_h4_method_contrasts(scale["scale_contrasts"])

        self.assertEqual(len(scale["scale_contrasts"]), 4)
        self.assertEqual(
            {row["baseline_method"] for row in planned["method_contrasts"]},
            {"full_schema", "lexical_top5", "dense_top5"},
        )
        self.assertTrue(
            all(
                row["h4_method_difference"] == 1
                for row in planned["method_contrasts"]
            )
        )

    def test_holm_adjustment_is_monotone_and_bounded(self):
        adjusted = holm_adjust({"a": 0.01, "b": 0.03, "c": 0.04})

        self.assertEqual(adjusted["a"], 0.03)
        self.assertEqual(adjusted["b"], 0.06)
        self.assertEqual(adjusted["c"], 0.06)

    def test_h3_runner_keeps_formal_model_and_cf11_open(self):
        records = []
        for task_index in range(8):
            for pool_repeat in ("A", "B", "C", "D", "E"):
                records += h3_triplet(
                    task_id=f"H3-{task_index}",
                    pool_repeat=pool_repeat,
                    functional_correct=False,
                    lexical_correct=True,
                    none_correct=True,
                )

        result = run_h3(document(records), n_resamples=20)

        self.assertEqual(result["descriptive_effect"]["estimate"], -1.0)
        self.assertEqual(result["formal_mixed_effect_model"]["status"], "not_run")
        self.assertEqual(result["cf11_status"], "in_progress")

    def test_h4_runner_applies_three_test_holm_family(self):
        records = []
        for task_index in range(8):
            for pool_repeat in ("A", "B", "C", "D", "E"):
                task_id = f"H4-{task_index}"
                records += h4_pair(
                    task_id=task_id,
                    pool_repeat=pool_repeat,
                    method="hierarchical",
                    correct_17=True,
                    correct_120=True,
                )
                for baseline in ("full_schema", "lexical_top5", "dense_top5"):
                    records += h4_pair(
                        task_id=task_id,
                        pool_repeat=pool_repeat,
                        method=baseline,
                        correct_17=True,
                        correct_120=False,
                    )

        result = run_h4(document(records), n_resamples=20)

        self.assertEqual(len(result["planned_comparisons"]), 3)
        self.assertTrue(result["paired_validation_support"])
        self.assertEqual(result["formal_mixed_effect_model"]["status"], "not_run")
        self.assertEqual(result["cf11_status"], "in_progress")


if __name__ == "__main__":
    unittest.main()
