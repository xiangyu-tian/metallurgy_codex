"""Aggregation order, repeat preservation and row-order invariance."""

import random
import unittest

from Tools.core_freeze.bootstrap_clusters import cluster_bootstrap
from Tools.core_freeze.build_paired_contrasts import (
    aggregate_pool_repeats,
    build_h3_pairs,
    overall_effect,
    run_repeat_summary,
)
from Tools.core_freeze.tests.fixtures import h3_triplet


class AggregationTests(unittest.TestCase):
    def setUp(self):
        self.records = []
        for run_repeat in (1, 2):
            for pool_repeat in ("A", "B", "C", "D", "E"):
                functional_correct = not (
                    run_repeat == 1 and pool_repeat in {"A", "B"}
                )
                self.records += h3_triplet(
                    functional_correct=functional_correct,
                    lexical_correct=True,
                    none_correct=True,
                    pool_repeat=pool_repeat,
                    model_run_repeat=run_repeat,
                )

    def _aggregate(self, records):
        pairs = build_h3_pairs(records)
        return aggregate_pool_repeats(pairs["direct_contrasts"], "d_h3")

    def test_pool_repeats_are_averaged_before_run_repeats(self):
        rows = self._aggregate(self.records)

        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["pool_repeats_complete"] for row in rows))
        summaries = run_repeat_summary(rows, "d_h3")
        self.assertEqual(summaries[0]["mean_effect"], -0.4)
        self.assertEqual(summaries[1]["mean_effect"], 0.0)
        self.assertEqual(overall_effect(rows, "d_h3"), -0.2)

    def test_row_order_does_not_change_effect_or_bootstrap(self):
        original = self._aggregate(self.records)
        shuffled_records = list(self.records)
        random.Random(17).shuffle(shuffled_records)
        shuffled = self._aggregate(shuffled_records)

        self.assertEqual(
            overall_effect(original, "d_h3"),
            overall_effect(shuffled, "d_h3"),
        )
        self.assertEqual(
            cluster_bootstrap(original, "d_h3", n_resamples=50, seed=9),
            cluster_bootstrap(shuffled, "d_h3", n_resamples=50, seed=9),
        )


if __name__ == "__main__":
    unittest.main()
