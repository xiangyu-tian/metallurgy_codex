import unittest
from collections import Counter

from Tools.core_freeze.prepare_cf05b_17_tool_review import (
    AI_FINDINGS,
    PRIMARY_REFERENCES,
)


class Cf05bReviewContractTests(unittest.TestCase):
    def test_review_covers_the_frozen_17_tool_baseline(self):
        expected_ids = {
            "A001",
            "A002",
            "A003",
            "A004",
            "A005",
            "B001",
            "B002",
            "B003",
            "B004",
            "B005",
            "B006",
            "B007",
            "B008",
            "B009",
            "B019",
            "C001",
            "C002",
        }
        self.assertEqual(set(AI_FINDINGS), expected_ids)

    def test_pre_review_counts_remain_explicit_and_non_accepting(self):
        dispositions = Counter(
            finding["ai_disposition"] for finding in AI_FINDINGS.values()
        )
        risks = Counter(finding["risk_level"] for finding in AI_FINDINGS.values())
        self.assertEqual(dispositions["revision_required_before_acceptance"], 14)
        self.assertEqual(dispositions["candidate_after_minor_clarification"], 3)
        self.assertEqual(risks["critical"], 5)
        self.assertNotIn(
            "accepted",
            {finding["ai_disposition"] for finding in AI_FINDINGS.values()},
        )

    def test_primary_scientific_references_are_https(self):
        self.assertGreaterEqual(len(PRIMARY_REFERENCES), 7)
        for url in PRIMARY_REFERENCES.values():
            self.assertTrue(url.startswith("https://"))


if __name__ == "__main__":
    unittest.main()
