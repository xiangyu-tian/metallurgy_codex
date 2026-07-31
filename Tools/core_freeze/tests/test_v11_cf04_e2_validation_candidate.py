import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.e2_contract_boundaries.build_e2_pilot_v2 import (
    reference_semantic_flags,
)
from Tools.core_freeze.e2_contract_boundaries.build_e2_validation_candidate import (
    DATASET_ID,
    HYBRID_POLICY_PATH,
    SPLIT_PATH,
    V2_TASKS_PATH,
    audit_independence,
    build_dataset,
    file_hash,
    load_json,
    review_v2_source,
    run_build,
)
from Tools.core_freeze.e2_contract_boundaries.hybrid_gate_v1 import (
    derive_structural_flags,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_PATH = (
    PROJECT_ROOT
    / "Tools"
    / "core_freeze"
    / "verified_core"
    / "contracts_v1.json"
)
OUTPUT_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "v11_cf04_e2_independent_validation_v1_candidate_20260731"
)


class V11Cf04E2ValidationCandidateTests(unittest.TestCase):
    def setUp(self):
        self.contracts = {
            row["tool_id"]: row
            for row in load_json(CONTRACTS_PATH)["contracts"]
        }
        self.hybrid_policy = load_json(HYBRID_POLICY_PATH)

    def test_v2_source_review_accepts_reproducible_candidate(self):
        review = review_v2_source()
        self.assertEqual(
            review["decision"],
            "accepted_as_locked_development_source_for_validation",
        )
        self.assertTrue(all(review["checks"].values()))
        self.assertFalse(review["core_frozen"])

    def test_validation_matrix_is_balanced_and_complete(self):
        tasks, events = build_dataset()
        self.assertEqual(len(tasks), 40)
        self.assertEqual(len(events), 45)
        self.assertEqual(
            {task["source_tool_id"] for task in tasks},
            set(self.contracts),
        )
        per_tool = {}
        for task in tasks:
            per_tool.setdefault(task["source_tool_id"], []).append(task)
        self.assertTrue(
            all(len(rows) == 8 for rows in per_tool.values())
        )
        semantic_allowed = set(self.hybrid_policy["semantic_flags"])
        positive = sum(
            any(flag in semantic_allowed for flag in task["expected_flags"])
            for task in tasks
        )
        self.assertEqual(positive, 20)
        self.assertEqual(len(tasks) - positive, 20)

    def test_validation_is_disjoint_from_development(self):
        tasks, events = build_dataset()
        audit = audit_independence(tasks, events)
        self.assertEqual(audit["status"], "candidate_passed")
        self.assertEqual(
            audit["summary"]["development_state_overlap_count"],
            0,
        )
        self.assertEqual(
            audit["summary"]["observability_error_count"],
            0,
        )
        self.assertTrue(all(row["passed"] for row in audit["checks"]))

    def test_base_task_and_group_ids_are_disjoint(self):
        development = load_json(V2_TASKS_PATH)["tasks"]
        validation, _ = build_dataset()
        self.assertFalse(
            {row["base_task_id"] for row in development}
            & {row["base_task_id"] for row in validation}
        )
        self.assertFalse(
            {row["base_task_group_id"] for row in development}
            & {row["base_task_group_id"] for row in validation}
        )

    def test_joint_tasks_have_observable_structural_and_semantic_flags(self):
        tasks, _ = build_dataset()
        joint = [
            task
            for task in tasks
            if task["mutation_types"]
            == [
                "make_parameter_ambiguous",
                "contract_out_of_domain",
            ]
        ]
        self.assertEqual(len(joint), 5)
        for task in joint:
            contract = self.contracts[task["source_tool_id"]]
            structural = derive_structural_flags(
                task["structured_state"],
                contract,
                self.hybrid_policy,
            )
            semantic = reference_semantic_flags(
                task["structured_state"],
                contract,
                self.hybrid_policy,
            )
            self.assertIn("ambiguous_parameter", structural)
            self.assertIn("contract_defined_out_of_domain", semantic)
            self.assertEqual(task["policy_expected_action"], "clarify")

    def test_output_package_is_hash_bound_and_not_executed(self):
        package = load_json(OUTPUT_DIR / "e2_validation_tasks_v1.json")
        self.assertEqual(package["dataset_id"], DATASET_ID)
        self.assertEqual(
            package["dataset_status"],
            "locked_validation_candidate_not_executed",
        )
        self.assertEqual(package["model_execution_count"], 0)
        manifest = load_json(OUTPUT_DIR / "artifact_manifest.json")
        self.assertFalse(manifest["external_api_execution_authorized"])
        for artifact in manifest["artifacts"]:
            self.assertEqual(
                file_hash(OUTPUT_DIR / artifact["filename"]),
                artifact["sha256"],
            )

    def test_split_is_locked_against_source_hashes(self):
        split = load_json(SPLIT_PATH)
        manifest = load_json(OUTPUT_DIR / "artifact_manifest.json")
        self.assertEqual(
            manifest["source_bindings"]["split_sha256"],
            file_hash(SPLIT_PATH),
        )
        self.assertFalse(split["external_api_execution_authorized"])
        self.assertEqual(split["model_execution_count"], 0)

    def test_builder_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "validation"
            report = run_build(output)
            self.assertEqual(report["status"], "candidate_passed")
            with self.assertRaises(FileExistsError):
                run_build(output)


if __name__ == "__main__":
    unittest.main()
