import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.e2_contract_boundaries.build_e2_hybrid_candidate import (
    V1_TASKS_PATH,
    V2_TASKS_PATH,
    audit_v1_observability,
    build_package,
    file_hash,
    load_json,
)
from Tools.core_freeze.e2_contract_boundaries.build_e2_pilot_v2 import (
    HYBRID_POLICY_PATH,
    build_dataset,
    reference_semantic_flags,
    validate_dataset,
)
from Tools.core_freeze.e2_contract_boundaries.hybrid_gate_v1 import (
    SEMANTIC_SCHEMA_PATH,
    derive_structural_flags,
    merge_flags,
    run_hybrid_gate,
    validate_semantic_output,
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
    / "v11_cf04_e2_hybrid_gate_v1_candidate_20260731"
)
V2_OUTPUT_DIR = V2_TASKS_PATH.parent


class V11Cf04E2HybridGateCandidateTests(unittest.TestCase):
    def setUp(self):
        self.contracts = {
            row["tool_id"]: row
            for row in load_json(CONTRACTS_PATH)["contracts"]
        }
        self.hybrid_policy = load_json(HYBRID_POLICY_PATH)
        self.semantic_schema = load_json(SEMANTIC_SCHEMA_PATH)

    def test_v1_defect_is_reproduced_on_exactly_four_tasks(self):
        report = audit_v1_observability(
            contracts=self.contracts,
            hybrid_policy=self.hybrid_policy,
        )
        self.assertEqual(report["status"], "defect_confirmed")
        self.assertEqual(report["mismatch_count"], 4)
        self.assertEqual(
            {row["task_id"] for row in report["mismatches"]},
            {
                "E2P-A001-11",
                "E2P-A002-09",
                "E2P-A003-09",
                "E2P-B019-12",
            },
        )

    def test_v2_rebuild_has_no_label_observability_mismatch(self):
        tasks, events = build_dataset()
        audit = validate_dataset(tasks, events)
        self.assertEqual(len(tasks), 55)
        self.assertEqual(len(events), 65)
        self.assertEqual(audit["status"], "candidate_passed")
        self.assertEqual(
            audit["summary"][
                "structural_observability_mismatch_count"
            ],
            0,
        )
        self.assertEqual(
            audit["summary"]["semantic_observability_mismatch_count"],
            0,
        )

    def test_joint_tasks_preserve_ambiguity_and_ood_evidence(self):
        tasks = load_json(V2_TASKS_PATH)["tasks"]
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
            self.assertIn("joint_mutation_spec_id", task)

    def test_semantic_schema_rejects_structural_and_decision_fields(self):
        self.assertEqual(
            validate_semantic_output(
                {"semantic_flags": []},
                self.semantic_schema,
            ),
            (True, []),
        )
        self.assertFalse(
            validate_semantic_output(
                {"semantic_flags": ["missing_parameter"]},
                self.semantic_schema,
            )[0]
        )
        self.assertFalse(
            validate_semantic_output(
                {"semantic_flags": [], "action": "call"},
                self.semantic_schema,
            )[0]
        )

    def test_merge_is_disjoint_ordered_and_policy_derived(self):
        merged = merge_flags(
            ["ambiguous_parameter", "unavailable"],
            ["contract_defined_out_of_domain"],
            self.hybrid_policy,
        )
        self.assertEqual(
            merged,
            [
                "ambiguous_parameter",
                "contract_defined_out_of_domain",
                "unavailable",
            ],
        )
        task = next(
            row
            for row in load_json(V2_TASKS_PATH)["tasks"]
            if row["mutation_types"]
            == [
                "make_parameter_ambiguous",
                "contract_out_of_domain",
            ]
        )
        result = run_hybrid_gate(
            structured_state=task["structured_state"],
            contract=self.contracts[task["source_tool_id"]],
            semantic_output={
                "semantic_flags": ["contract_defined_out_of_domain"]
            },
        )
        self.assertEqual(result["policy_expected_action"], "clarify")

    def test_candidate_package_is_local_only_and_hash_bound(self):
        report = load_json(OUTPUT_DIR / "candidate_report.json")
        self.assertEqual(
            report["status"],
            "local_candidate_prepared_not_authorized",
        )
        self.assertEqual(report["external_api_calls"], 0)
        self.assertFalse(report["external_api_execution_authorized"])
        self.assertFalse(report["model_performance_claim_allowed"])
        self.assertTrue(
            report["offline_pipeline"]["oracle_semantic_flags_used"]
        )
        manifest = load_json(OUTPUT_DIR / "artifact_manifest.json")
        for artifact in manifest["artifacts"]:
            self.assertEqual(
                file_hash(OUTPUT_DIR / artifact["filename"]),
                artifact["sha256"],
            )
        for directory in (OUTPUT_DIR, V2_OUTPUT_DIR):
            combined = "\n".join(
                path.read_text(encoding="utf-8")
                for path in directory.iterdir()
                if path.is_file()
            )
            self.assertNotIn("sk-", combined)

    def test_builders_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "candidate"
            report = build_package(output)
            self.assertEqual(report["external_api_calls"], 0)
            with self.assertRaises(FileExistsError):
                build_package(output)

    def test_v1_and_v2_are_separate_versioned_datasets(self):
        v1 = load_json(V1_TASKS_PATH)
        v2 = load_json(V2_TASKS_PATH)
        self.assertNotEqual(v1["dataset_id"], v2["dataset_id"])
        self.assertTrue(
            all(task["task_id"].startswith("E2V2-") for task in v2["tasks"])
        )
        self.assertTrue(
            all(task["task_id"].startswith("E2P-") for task in v1["tasks"])
        )


if __name__ == "__main__":
    unittest.main()
