import copy
import json
import tempfile
import unittest
from pathlib import Path

from Tools.core_freeze.e3_routing import build_e3_a003_controlled_pools as builder


class V11Cf05E3A003ControlledPoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = builder.load_json(builder.CONFIG_PATH)
        cls.result = builder.build(cls.config)
        cls.records = cls.result["manifest"]["records"]

    def test_all_bound_inputs_are_immutable(self):
        for binding in self.config["bindings"].values():
            builder.validate_bound_file(binding)

    def test_exact_design_grid_is_constructed(self):
        self.assertEqual(len(self.records), 100)
        observed = {
            (
                row["pool_repeat"],
                row["tool_pool_size"],
                row["near_neighbor_type"],
                row["near_neighbor_count"],
            )
            for row in self.records
        }
        expected = {
            (
                repeat,
                size,
                condition["near_neighbor_type"],
                condition["near_neighbor_count"],
            )
            for repeat in self.config["pool_repeats"]
            for size in self.config["pool_sizes"]
            for condition in self.config["conditions"]
        }
        self.assertEqual(observed, expected)

    def test_every_pool_has_exact_size_target_and_dose(self):
        assigned = set(self.config["lexical_neighbor_ids"]) | set(
            self.config["contract_mismatch_neighbor_ids"]
        )
        for row in self.records:
            self.assertEqual(len(row["tool_order"]), row["tool_pool_size"])
            self.assertEqual(len(set(row["tool_order"])), row["tool_pool_size"])
            self.assertEqual(row["tool_order"].count("A003"), 1)
            self.assertEqual(
                set(row["tool_order"]) & assigned,
                set(row["near_neighbor_tool_ids"]),
            )
            self.assertEqual(
                len(row["near_neighbor_tool_ids"]), row["near_neighbor_count"]
            )

    def test_paired_neighbor_types_share_neutral_base_and_slots(self):
        for repeat in self.config["pool_repeats"]:
            for size in self.config["pool_sizes"]:
                for count in (4, 8):
                    pair = [
                        row
                        for row in self.records
                        if row["pool_repeat"] == repeat
                        and row["tool_pool_size"] == size
                        and row["near_neighbor_count"] == count
                    ]
                    self.assertEqual(len(pair), 2)
                    self.assertEqual(pair[0]["neutral_tool_ids"], pair[1]["neutral_tool_ids"])
                    self.assertEqual(
                        pair[0]["neighbor_slot_positions_1_based"],
                        pair[1]["neighbor_slot_positions_1_based"],
                    )

    def test_each_repeat_condition_is_nested_across_sizes(self):
        for repeat in self.config["pool_repeats"]:
            for condition in self.config["conditions"]:
                rows = sorted(
                    (
                        row
                        for row in self.records
                        if row["pool_repeat"] == repeat
                        and row["near_neighbor_type"]
                        == condition["near_neighbor_type"]
                        and row["near_neighbor_count"]
                        == condition["near_neighbor_count"]
                    ),
                    key=lambda row: row["tool_pool_size"],
                )
                self.assertEqual([row["tool_pool_size"] for row in rows], [17, 50, 100, 120])
                for left, right in zip(rows, rows[1:]):
                    self.assertTrue(set(left["tool_order"]).issubset(right["tool_order"]))

    def test_registered_target_positions_and_four_dose_balance(self):
        for row in self.records:
            expected = self.config["target_position_1_based"][
                str(row["tool_pool_size"])
            ][row["pool_repeat"]]
            self.assertEqual(row["target_position_1_based"], expected)
        balance = self.result["audit"]["four_dose_selection_frequency"]
        for frequencies in balance.values():
            self.assertLessEqual(max(frequencies.values()) - min(frequencies.values()), 1)

    def test_proxy_semantics_are_explicit_and_nonformal(self):
        assignment = self.result["assignment"]
        report = self.result["report"]
        self.assertEqual(
            assignment["functional_overlap_operationalization"],
            "contract_mismatch_proxy",
        )
        self.assertFalse(assignment["expert_validated_functional_overlap"])
        self.assertFalse(assignment["confirmatory_use_allowed"])
        self.assertFalse(report["formal_pool_generation_allowed"])
        self.assertFalse(report["confirmatory_use_allowed"])
        self.assertEqual(report["external_api_calls"], 0)
        self.assertEqual(report["cf05_status"], "in_progress")
        self.assertFalse(report["core_frozen"])

    def test_neutral_screening_excludes_accidental_a003_neighbors(self):
        neutral = self.result["audit"]["neutral_universe"]
        self.assertEqual(
            neutral["safe_candidate_ids"],
            self.config["expected_safe_neutral_candidate_ids"],
        )
        self.assertEqual(
            [row["candidate_tool_id"] for row in neutral["additional_a003_screening_exclusions"]],
            self.config["expected_additional_a003_screening_exclusions"],
        )
        self.assertGreaterEqual(neutral["count"], 120)

    def test_schema_registry_covers_every_pool_tool(self):
        used = {tool_id for row in self.records for tool_id in row["tool_order"]}
        registered = {
            row["tool_id"] for row in self.result["schema_registry"]["entries"]
        }
        self.assertEqual(used, registered)
        self.assertEqual(len(registered), self.result["report"]["schema_registry_entry_count"])

    def test_policy_mutations_are_rejected(self):
        for field in (
            "formal_catalog_mutation_allowed",
            "formal_pool_generation_allowed",
            "external_api_calls_authorized",
            "expert_validated_functional_overlap",
            "confirmatory_use_allowed",
        ):
            invalid = copy.deepcopy(self.config)
            invalid[field] = True
            with self.assertRaisesRegex(ValueError, "must remain false"):
                builder.build(invalid)

    def test_design_grid_mutations_are_rejected(self):
        invalid_sizes = copy.deepcopy(self.config)
        invalid_sizes["pool_sizes"] = [17, 50, 120]
        with self.assertRaisesRegex(ValueError, "pool_sizes must remain"):
            builder.build(invalid_sizes)

        invalid_repeats = copy.deepcopy(self.config)
        invalid_repeats["pool_repeats"] = ["A", "B"]
        with self.assertRaisesRegex(ValueError, "pool_repeats must remain"):
            builder.build(invalid_repeats)

        invalid_conditions = copy.deepcopy(self.config)
        invalid_conditions["conditions"][3]["near_neighbor_type"] = "contract_mismatch"
        with self.assertRaisesRegex(ValueError, "conditions must remain"):
            builder.build(invalid_conditions)

    def test_fresh_output_has_complete_hash_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "pools"
            report = builder.build_outputs(output_dir)
            self.assertEqual(report, self.result["report"])
            manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["artifact_count"], 6)
            for row in manifest["artifacts"]:
                path = output_dir / row["filename"]
                self.assertTrue(path.is_file())
                self.assertEqual(builder.sha256_file(path), row["sha256"])
                self.assertEqual(path.stat().st_size, row["bytes"])


if __name__ == "__main__":
    unittest.main()
