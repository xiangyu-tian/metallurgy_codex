"""Positive, negative and zero paired contrasts."""

import unittest

from Tools.core_freeze.build_paired_contrasts import (
    build_h3_pairs,
    build_h4_scale_pairs,
)
from Tools.core_freeze.tests.fixtures import h3_triplet, h4_pair


class PairingTests(unittest.TestCase):
    def test_h3_preserves_negative_positive_and_zero_differences(self):
        records = []
        records += h3_triplet(
            task_id="NEGATIVE",
            functional_correct=False,
            lexical_correct=True,
            none_correct=True,
        )
        records += h3_triplet(
            task_id="POSITIVE",
            functional_correct=True,
            lexical_correct=False,
            none_correct=True,
        )
        records += h3_triplet(
            task_id="ZERO",
            functional_correct=True,
            lexical_correct=True,
            none_correct=True,
        )

        result = build_h3_pairs(records)
        effects = {
            row["task_id"]: row["d_h3"] for row in result["direct_contrasts"]
        }

        self.assertEqual(effects, {"NEGATIVE": -1, "POSITIVE": 1, "ZERO": 0})
        self.assertEqual(result["missing_pairs"], [])

    def test_h4_pairs_120_and_17_within_the_same_unit(self):
        result = build_h4_scale_pairs(
            h4_pair(
                method="hierarchical",
                correct_17=True,
                correct_120=False,
            )
        )

        self.assertEqual(len(result["scale_contrasts"]), 1)
        self.assertEqual(result["scale_contrasts"][0]["d_h4"], -1)
        self.assertEqual(result["missing_pairs"], [])


if __name__ == "__main__":
    unittest.main()
