"""Missing pairs and split request/execution state semantics."""

import copy
import unittest

from Tools.core_freeze.analysis_core import selection_correct, validate_document
from Tools.core_freeze.build_paired_contrasts import build_h3_pairs
from Tools.core_freeze.tests.fixtures import document, h3_triplet, record


class MissingnessTests(unittest.TestCase):
    def test_missing_h3_condition_is_audited_not_imputed(self):
        records = h3_triplet(
            functional_correct=False,
            lexical_correct=True,
            none_correct=True,
        )
        records = [
            row for row in records if row["near_neighbor_type"] != "lexical"
        ]

        result = build_h3_pairs(records)

        self.assertEqual(result["direct_contrasts"], [])
        self.assertEqual(result["missing_pairs"][0]["missing"], ["lexical_8"])

    def test_not_accepted_request_requires_null_execution_fields(self):
        valid = record(
            request_status="not_accepted",
            execution_status=None,
        )
        self.assertEqual(validate_document(document([valid])), [])
        self.assertIsNone(selection_correct(valid))

        invalid = copy.deepcopy(valid)
        invalid["execution_status"] = "provider_failure"
        errors = validate_document(document([invalid]))
        self.assertTrue(
            any("not_accepted requests require execution_status=null" in error for error in errors)
        )

    def test_provider_failure_is_not_fabricated_as_selection_result(self):
        failed = record(execution_status="provider_failure", correct=False)

        self.assertEqual(validate_document(document([failed])), [])
        self.assertIsNone(selection_correct(failed))
        self.assertFalse(failed["end_to_end_correct"])

    def test_validator_reports_wrong_types_without_crashing(self):
        invalid = record()
        invalid["request_status"] = []
        invalid["end_to_end_correct"] = 1

        errors = validate_document(document([invalid]))

        self.assertTrue(any("request_status: unsupported status" in error for error in errors))
        self.assertTrue(any("end_to_end_correct" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
