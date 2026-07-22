"""热力学模型在数据库不可用时必须使用内置可信数据。"""

import os
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models_core import ModelRegistry
from models_core.chemical_data import find_reaction
import models_core.models_b as models_b
from models_core.repositories.thermodynamic_repository import repo


class ThermodynamicFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ModelRegistry()
        cls.registry.discover()

    def test_shomate_uses_builtin_data_without_database_driver(self):
        with patch.object(repo, "find_correlation", return_value=None), \
                patch.object(repo, "get_property", return_value=None):
            result = self.registry.invoke(
                "B001", {"species": "Fe(s)", "temperature": 1000}
            )

        self.assertTrue(result.success, result.error)
        self.assertAlmostEqual(result.result["Cp"], 35.47286, places=5)
        self.assertEqual(result.result["data_source"], "builtin_fallback")

    def test_reaction_gibbs_uses_builtin_data_without_database_driver(self):
        with patch.object(
            models_b,
            "_lookup_reaction",
            side_effect=lambda reaction, temperature=298.15: find_reaction(reaction),
        ):
            result = self.registry.invoke(
                "B008", {"reaction": "C + O₂ → CO₂", "temperature": 1000}
            )

        self.assertTrue(result.success, result.error)
        self.assertAlmostEqual(result.result["delta_G"], -396.4, places=1)


if __name__ == "__main__":
    unittest.main()
