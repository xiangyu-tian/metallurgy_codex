import copy
import json
import shutil
import unittest
import uuid

try:
    import fastembed  # noqa: F401
    import numpy as np
except ImportError as exc:  # the dense candidate intentionally uses an isolated runtime
    raise unittest.SkipTest(
        "A003 Dense Top-5 tests require Tools/core_freeze/e3_routing/"
        "dense_validation_requirements_lock.txt"
    ) from exc

from Tools.core_freeze.e3_routing import build_e3_a003_dense_top5_candidate as builder


class V11Cf05E3A003DenseTop5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = builder.load_json(builder.CONFIG_PATH)
        cls.built = builder.build(cls.config)

    def test_inputs_runtime_and_model_are_hash_bound(self):
        for binding in self.config["bindings"].values():
            builder.validate_binding(binding)
        self.assertTrue(self.built["runtime_audit"]["all_locked_versions_match"])
        self.assertTrue(
            self.built["model_audit"]["all_expected_files_present_and_hash_valid"]
        )
        self.assertEqual(len(self.built["model_audit"]["files"]), 5)

    def test_frozen_vectors_cover_registry(self):
        snapshot = self.built["index_snapshot"]
        self.assertEqual(snapshot["document_count"], 137)
        self.assertEqual(snapshot["embedding_dimension"], 512)
        self.assertEqual(self.built["vectors"].shape, (137, 512))
        self.assertEqual(self.built["vectors"].dtype, np.float32)
        norms = np.linalg.norm(self.built["vectors"], axis=1)
        self.assertTrue(np.allclose(norms, 1.0, atol=1e-6))
        self.assertEqual(len(snapshot["vector_sha256"]), 64)

    def test_contract_documents_are_gold_blind(self):
        documents = self.built["documents"]
        self.assertEqual(documents["document_count"], 137)
        serialized = builder.canonical_json(documents)
        for field in (
            "acceptable_tools",
            "revalidated_primary_acceptable_tools",
            "scoring_rule",
            "expected_parameters",
        ):
            self.assertNotIn(f'"{field}"', serialized)
        self.assertIn("calc_molar_mass", serialized)

    def test_exact_24_pool_constrained_top5_views(self):
        views = self.built["candidate_views"]["views"]
        self.assertEqual(len(views), 24)
        pools = builder.load_json(
            builder.validate_binding(self.config["bindings"]["routing_selected_pools"])
        )
        pool_by_id = {row["pool_id"]: row for row in pools["pools"]}
        for view in views:
            self.assertEqual(len(view["candidate_tool_ids"]), 5)
            self.assertEqual(len(set(view["candidate_tool_ids"])), 5)
            self.assertTrue(
                set(view["candidate_tool_ids"]).issubset(
                    pool_by_id[view["pool_id"]]["tool_order"]
                )
            )

    def test_embeddings_and_rankings_are_deterministic(self):
        audit = self.built["determinism"]
        self.assertTrue(audit["all_query_embedding_repeats_exactly_equal"])
        self.assertTrue(audit["all_ranking_repeats_equal"])
        self.assertEqual(len(audit["query_embeddings"]), 2)
        self.assertEqual(len(audit["rankings"]), 24)

    def test_local_promotion_gate_passes_without_external_calls(self):
        report = self.built["readiness"]
        self.assertEqual(
            report["implementation_status"],
            "candidate_implementation_passed_local_gate",
        )
        self.assertTrue(report["ready_for_24_cell_dense_slice_generation"])
        self.assertFalse(report["ready_for_external_development_run"])
        self.assertEqual(
            report["observed_development_metrics"]["acceptable_recall_at_5"], 1.0
        )
        self.assertEqual(
            report["observed_development_metrics"]["target_recall_at_5"], 1.0
        )
        self.assertEqual(self.built["candidate_views"]["external_api_calls"], 0)
        self.assertEqual(self.built["candidate_views"]["tool_calls_executed"], 0)

    def test_policy_and_model_mutations_are_rejected(self):
        for field in (
            "gold_visible_to_retriever",
            "external_api_calls_authorized",
            "tool_execution_allowed",
            "confirmatory_inference_allowed",
            "independent_validation_split_access_allowed",
            "core_frozen",
        ):
            invalid = copy.deepcopy(self.config)
            invalid[field] = True
            with self.assertRaisesRegex(ValueError, "must remain false"):
                builder.build(invalid)
        invalid = copy.deepcopy(self.config)
        invalid["embedding_model"]["dimension"] = 768
        with self.assertRaisesRegex(ValueError, "frozen embedding model field changed"):
            builder.build(invalid)

    def test_fresh_output_manifest_and_vector_archive_are_complete(self):
        output_dir = (
            builder.WORKSPACE / "outputs" / f".a003-dense-top5-test-{uuid.uuid4().hex}"
        )
        try:
            builder.build_outputs(output_dir)
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["artifact_count"], 10)
            for row in manifest["artifacts"]:
                path = output_dir / row["filename"]
                self.assertEqual(builder.sha256_file(path), row["sha256"])
                self.assertEqual(path.stat().st_size, row["bytes"])
            with np.load(output_dir / "a003_dense_top5_vectors.npz") as archive:
                self.assertEqual(archive["vectors"].shape, (137, 512))
                self.assertEqual(archive["tool_ids"].shape, (137,))
        finally:
            if output_dir.exists():
                shutil.rmtree(output_dir)


if __name__ == "__main__":
    unittest.main()
