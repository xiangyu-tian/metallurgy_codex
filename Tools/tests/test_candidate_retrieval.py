"""Contract and dataset-level tests for M4.6B candidate model retrieval."""

import os
import sys
import unittest


TOOLS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, TOOLS_DIR)

from models_core import ModelRegistry
from models_core.benchmarking import ToolCallingDataset
from models_core.candidate_retrieval import (
    CandidateModelRetriever,
    evaluate_candidate_retrieval,
)


class CandidateModelRetrieverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ModelRegistry()
        cls.registry.discover()
        cls.retriever = CandidateModelRetriever(cls.registry)

    def test_retrieve_returns_ranked_explainable_top_k_contract(self):
        result = self.retriever.retrieve(
            "先把 800 摄氏度换算为开尔文，再用 Arrhenius 公式求速率常数。",
            top_k=5,
        )

        self.assertEqual(result["strategy"], "lexical-card-v1")
        self.assertEqual(result["top_k"], 5)
        self.assertFalse(result["fallback_used"])
        self.assertLessEqual(len(result["candidate_models"]), 5)
        codes = [item["model_code"] for item in result["candidate_models"]]
        self.assertIn("A001", codes)
        self.assertIn("C001", codes)
        self.assertEqual(
            [item["rank"] for item in result["candidate_models"]],
            list(range(1, len(result["candidate_models"]) + 1)),
        )
        self.assertEqual(
            [item["score"] for item in result["candidate_models"]],
            sorted(
                [item["score"] for item in result["candidate_models"]],
                reverse=True,
            ),
        )
        for item in result["candidate_models"]:
            self.assertTrue(item["matched_terms"])
            self.assertTrue(item["reason"])

    def test_no_match_without_calculation_intent_offers_no_tools(self):
        result = self.retriever.retrieve("介绍钢铁工业的发展历史。", top_k=5)

        self.assertEqual(result["candidate_models"], [])
        self.assertFalse(result["fallback_used"])
        self.assertEqual(result["fallback_reason"], "no_tool_signal")

    def test_unmatched_calculation_intent_falls_back_to_all_tools(self):
        result = self.retriever.retrieve("计算这个尚未注册的冶金指标数值。", top_k=5)

        self.assertTrue(result["fallback_used"])
        self.assertEqual(result["fallback_reason"], "calculation_intent_without_match")
        self.assertEqual(len(result["candidate_models"]), 17)

    def test_v120_dataset_meets_frozen_top5_retrieval_gates(self):
        result = evaluate_candidate_retrieval(
            ToolCallingDataset(),
            self.retriever,
            top_k=5,
        )
        summary = result["summary"]

        self.assertEqual(result["dataset_version"], "1.2.0")
        self.assertGreaterEqual(summary["single_required_complete_recall"], 0.98)
        self.assertEqual(summary["multi_tool_complete_recall"], 1.0)
        self.assertLessEqual(summary["average_candidate_count"], 5.0)
        self.assertLessEqual(summary["fallback_rate"], 0.1)


if __name__ == "__main__":
    unittest.main()
