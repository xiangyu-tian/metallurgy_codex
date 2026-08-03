"""Callable wrappers for nonformal E3 registration candidates."""

from __future__ import annotations

import math
from typing import Any, Callable

from Tools.core_freeze.e3_routing import pint_unit_adapter


def _failure(code: str, message: str) -> dict[str, Any]:
    return {"success": False, "result": None, "error_code": code, "error": message}


def _require_exact_object(params: Any, required: set[str]) -> dict[str, Any] | None:
    if not isinstance(params, dict) or set(params) != required:
        return None
    return params


def invoke_pint_unit_conversion(params: dict[str, Any]) -> dict[str, Any]:
    return pint_unit_adapter.invoke(params)


def invoke_pymatgen_formula_parser(params: dict[str, Any]) -> dict[str, Any]:
    validated = _require_exact_object(params, {"formula"})
    if validated is None or not isinstance(validated["formula"], str) or not validated["formula"]:
        return _failure("INVALID_INPUT", "formula must be a non-empty string")
    try:
        from pymatgen.core import Composition

        composition = Composition(validated["formula"])
        return {
            "success": True,
            "result": {"elements": composition.get_el_amt_dict()},
            "error_code": None,
            "error": None,
        }
    except Exception as exc:
        return _failure("PARSE_ERROR", f"{type(exc).__name__}: {str(exc)[:240]}")


def invoke_rdkit_average_molecular_weight(params: dict[str, Any]) -> dict[str, Any]:
    validated = _require_exact_object(params, {"smiles"})
    if validated is None or not isinstance(validated["smiles"], str) or not validated["smiles"]:
        return _failure("INVALID_INPUT", "smiles must be a non-empty string")
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors

        molecule = Chem.MolFromSmiles(validated["smiles"])
        if molecule is None:
            return _failure("PARSE_ERROR", "RDKit rejected the SMILES input")
        return {
            "success": True,
            "result": {"molar_mass": float(Descriptors.MolWt(molecule)), "unit": "g/mol"},
            "error_code": None,
            "error": None,
        }
    except Exception as exc:
        return _failure("EXECUTION_ERROR", f"{type(exc).__name__}: {str(exc)[:240]}")


def invoke_pymatgen_composition_weight(params: dict[str, Any]) -> dict[str, Any]:
    validated = _require_exact_object(params, {"formula"})
    if validated is None or not isinstance(validated["formula"], str) or not validated["formula"]:
        return _failure("INVALID_INPUT", "formula must be a non-empty string")
    try:
        from pymatgen.core import Composition

        composition = Composition(validated["formula"])
        return {
            "success": True,
            "result": {"molar_mass": float(composition.weight), "unit": "g/mol"},
            "error_code": None,
            "error": None,
        }
    except Exception as exc:
        return _failure("PARSE_ERROR", f"{type(exc).__name__}: {str(exc)[:240]}")


def invoke_pymatgen_fractional_composition(params: dict[str, Any]) -> dict[str, Any]:
    validated = _require_exact_object(params, {"compositions"})
    if validated is None or not isinstance(validated["compositions"], dict):
        return _failure("INVALID_INPUT", "compositions must be an object")
    try:
        from pymatgen.core import Composition

        composition = Composition(validated["compositions"])
        return {
            "success": True,
            "result": {"normalized": composition.fractional_composition.get_el_amt_dict()},
            "error_code": None,
            "error": None,
        }
    except Exception as exc:
        return _failure("NORMALIZATION_ERROR", f"{type(exc).__name__}: {str(exc)[:240]}")


def _require_object_with_optional(
    params: Any,
    required: set[str],
    optional: set[str],
) -> dict[str, Any] | None:
    if not isinstance(params, dict):
        return None
    keys = set(params)
    if not required.issubset(keys) or not keys.issubset(required | optional):
        return None
    return params


def invoke_pint_context_transform(params: dict[str, Any]) -> dict[str, Any]:
    validated = _require_object_with_optional(
        params,
        {"value", "source_unit", "target_unit", "context_name"},
        {"context_parameters"},
    )
    if validated is None:
        return _failure("INVALID_INPUT", "context conversion fields do not match the contract")
    if not isinstance(validated["value"], (int, float)) or isinstance(validated["value"], bool):
        return _failure("INVALID_INPUT", "value must be numeric")
    if not math.isfinite(float(validated["value"])):
        return _failure("INVALID_INPUT", "value must be finite")
    if not all(
        isinstance(validated[name], str) and validated[name]
        for name in ("source_unit", "target_unit", "context_name")
    ):
        return _failure("INVALID_INPUT", "unit and context names must be non-empty strings")
    context_parameters = validated.get("context_parameters", {})
    if not isinstance(context_parameters, dict):
        return _failure("INVALID_INPUT", "context_parameters must be an object")
    try:
        from pint import UnitRegistry

        registry = UnitRegistry()
        quantity = float(validated["value"]) * registry(validated["source_unit"])
        converted = quantity.to(
            validated["target_unit"],
            validated["context_name"],
            **context_parameters,
        )
        return {
            "success": True,
            "result": {
                "converted_value": float(converted.magnitude),
                "target_unit": str(converted.units),
                "context_name": validated["context_name"],
            },
            "error_code": None,
            "error": None,
        }
    except KeyError as exc:
        return _failure("UNDEFINED_CONTEXT", f"{type(exc).__name__}: {str(exc)[:240]}")
    except Exception as exc:
        return _failure("CONTEXT_TRANSFORM_ERROR", f"{type(exc).__name__}: {str(exc)[:240]}")


def invoke_rdkit_smiles_parser(params: dict[str, Any]) -> dict[str, Any]:
    validated = _require_object_with_optional(params, {"smiles"}, {"sanitize"})
    if validated is None or not isinstance(validated["smiles"], str) or not validated["smiles"]:
        return _failure("INVALID_INPUT", "smiles must be a non-empty string")
    sanitize = validated.get("sanitize", True)
    if not isinstance(sanitize, bool):
        return _failure("INVALID_INPUT", "sanitize must be boolean")
    try:
        from rdkit import Chem

        molecule = Chem.MolFromSmiles(validated["smiles"], sanitize=sanitize)
        if molecule is None:
            return _failure("SMILES_PARSE_ERROR", "RDKit rejected the SMILES input")
        return {
            "success": True,
            "result": {
                "canonical_smiles": Chem.MolToSmiles(molecule, canonical=True),
                "atom_count": molecule.GetNumAtoms(),
                "bond_count": molecule.GetNumBonds(),
                "formal_charge": Chem.GetFormalCharge(molecule),
            },
            "error_code": None,
            "error": None,
        }
    except Exception as exc:
        return _failure("SMILES_PARSE_ERROR", f"{type(exc).__name__}: {str(exc)[:240]}")


def invoke_rdkit_smarts_parser(params: dict[str, Any]) -> dict[str, Any]:
    validated = _require_object_with_optional(params, {"smarts"}, {"merge_hydrogens"})
    if validated is None or not isinstance(validated["smarts"], str) or not validated["smarts"]:
        return _failure("INVALID_INPUT", "smarts must be a non-empty string")
    merge_hydrogens = validated.get("merge_hydrogens", False)
    if not isinstance(merge_hydrogens, bool):
        return _failure("INVALID_INPUT", "merge_hydrogens must be boolean")
    try:
        from rdkit import Chem

        molecule = Chem.MolFromSmarts(validated["smarts"], mergeHs=merge_hydrogens)
        if molecule is None:
            return _failure("SMARTS_PARSE_ERROR", "RDKit rejected the SMARTS input")
        return {
            "success": True,
            "result": {
                "canonical_smarts": Chem.MolToSmarts(molecule),
                "query_atom_count": molecule.GetNumAtoms(),
                "query_bond_count": molecule.GetNumBonds(),
            },
            "error_code": None,
            "error": None,
        }
    except Exception as exc:
        return _failure("SMARTS_PARSE_ERROR", f"{type(exc).__name__}: {str(exc)[:240]}")


def invoke_rdkit_canonical_smiles(params: dict[str, Any]) -> dict[str, Any]:
    validated = _require_object_with_optional(params, {"smiles"}, {"use_chirality"})
    if validated is None or not isinstance(validated["smiles"], str) or not validated["smiles"]:
        return _failure("INVALID_INPUT", "smiles must be a non-empty string")
    use_chirality = validated.get("use_chirality", True)
    if not isinstance(use_chirality, bool):
        return _failure("INVALID_INPUT", "use_chirality must be boolean")
    try:
        from rdkit import Chem

        return {
            "success": True,
            "result": {"canonical_smiles": Chem.CanonSmiles(validated["smiles"], useChiral=use_chirality)},
            "error_code": None,
            "error": None,
        }
    except Exception as exc:
        return _failure("CANONICALIZATION_ERROR", f"{type(exc).__name__}: {str(exc)[:240]}")


def _rdkit_descriptor(params: dict[str, Any], descriptor_name: str) -> dict[str, Any]:
    validated = _require_exact_object(params, {"smiles"})
    if validated is None or not isinstance(validated["smiles"], str) or not validated["smiles"]:
        return _failure("INVALID_INPUT", "smiles must be a non-empty string")
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors

        molecule = Chem.MolFromSmiles(validated["smiles"])
        if molecule is None:
            return _failure("SMILES_PARSE_ERROR", "RDKit rejected the SMILES input")
        if descriptor_name == "exact":
            value = float(Descriptors.ExactMolWt(molecule))
            result = {"exact_molecular_weight": value, "mass_convention": "exact_isotopic_mass"}
        else:
            value = float(Descriptors.HeavyAtomMolWt(molecule))
            result = {"heavy_atom_molecular_weight": value, "hydrogen_excluded": True}
        return {"success": True, "result": result, "error_code": None, "error": None}
    except Exception as exc:
        return _failure("DESCRIPTOR_ERROR", f"{type(exc).__name__}: {str(exc)[:240]}")


def invoke_rdkit_exact_molecular_weight(params: dict[str, Any]) -> dict[str, Any]:
    return _rdkit_descriptor(params, "exact")


def invoke_rdkit_heavy_atom_molecular_weight(params: dict[str, Any]) -> dict[str, Any]:
    return _rdkit_descriptor(params, "heavy")


def _pymatgen_composition(value: Any):
    from pymatgen.core import Composition

    if not isinstance(value, (str, dict)):
        raise TypeError("formula_or_amounts must be a string or object")
    if isinstance(value, str) and not value:
        raise ValueError("formula_or_amounts must not be empty")
    if isinstance(value, dict) and not value:
        raise ValueError("formula_or_amounts must not be empty")
    return Composition(value)


def invoke_pymatgen_reduced_composition(params: dict[str, Any]) -> dict[str, Any]:
    validated = _require_exact_object(params, {"formula_or_amounts"})
    if validated is None:
        return _failure("INVALID_INPUT", "formula_or_amounts is required")
    try:
        reduced, factor = _pymatgen_composition(validated["formula_or_amounts"]).get_reduced_composition_and_factor()
        return {
            "success": True,
            "result": {
                "reduced_formula": reduced.reduced_formula,
                "reduced_amounts": reduced.get_el_amt_dict(),
                "reduction_factor": float(factor),
            },
            "error_code": None,
            "error": None,
        }
    except Exception as exc:
        return _failure("REDUCTION_ERROR", f"{type(exc).__name__}: {str(exc)[:240]}")


def _pymatgen_species_fraction(params: dict[str, Any], basis: str) -> dict[str, Any]:
    validated = _require_exact_object(params, {"formula_or_amounts", "species"})
    if validated is None or not isinstance(validated["species"], str) or not validated["species"]:
        return _failure("INVALID_INPUT", "formula_or_amounts and species are required")
    try:
        from pymatgen.core import Element

        composition = _pymatgen_composition(validated["formula_or_amounts"])
        species = Element(validated["species"])
        if composition[species] <= 0:
            return _failure("UNKNOWN_SPECIES", "selected species is absent from the composition")
        if basis == "atomic":
            result = {"species": validated["species"], "atomic_fraction": float(composition.get_atomic_fraction(species))}
        else:
            result = {"species": validated["species"], "weight_fraction": float(composition.get_wt_fraction(species))}
        return {"success": True, "result": result, "error_code": None, "error": None}
    except ValueError as exc:
        return _failure("UNKNOWN_SPECIES", f"{type(exc).__name__}: {str(exc)[:240]}")
    except Exception as exc:
        return _failure("COMPOSITION_PARSE_ERROR", f"{type(exc).__name__}: {str(exc)[:240]}")


def invoke_pymatgen_atomic_fraction(params: dict[str, Any]) -> dict[str, Any]:
    return _pymatgen_species_fraction(params, "atomic")


def invoke_pymatgen_weight_fraction(params: dict[str, Any]) -> dict[str, Any]:
    return _pymatgen_species_fraction(params, "weight")


def invoke_pymatgen_weight_to_molar(params: dict[str, Any]) -> dict[str, Any]:
    validated = _require_exact_object(params, {"weights"})
    if validated is None or not isinstance(validated["weights"], dict) or not validated["weights"]:
        return _failure("INVALID_WEIGHT_MAPPING", "weights must be a non-empty object")
    values = list(validated["weights"].values())
    if any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) < 0
        for value in values
    ) or not any(float(value) > 0 for value in values):
        return _failure("INVALID_WEIGHT_MAPPING", "weights must be finite, nonnegative, and not all zero")
    try:
        from pymatgen.core import Composition

        composition = Composition.from_weight_dict(validated["weights"])
        return {
            "success": True,
            "result": {
                "molar_amounts": composition.get_el_amt_dict(),
                "atomic_fractions": composition.fractional_composition.get_el_amt_dict(),
            },
            "error_code": None,
            "error": None,
        }
    except Exception as exc:
        return _failure("CONVERSION_ERROR", f"{type(exc).__name__}: {str(exc)[:240]}")


ADAPTERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "E3C001": invoke_pint_unit_conversion,
    "E3C002": invoke_pymatgen_formula_parser,
    "E3C003": invoke_rdkit_average_molecular_weight,
    "E3C004": invoke_pymatgen_composition_weight,
    "E3C005": invoke_pymatgen_fractional_composition,
}


BATCH2_ADAPTERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "E3C006": invoke_pint_context_transform,
    "E3C007": invoke_rdkit_smiles_parser,
    "E3C008": invoke_rdkit_smarts_parser,
    "E3C009": invoke_rdkit_canonical_smiles,
    "E3C010": invoke_rdkit_exact_molecular_weight,
    "E3C011": invoke_rdkit_heavy_atom_molecular_weight,
    "E3C012": invoke_pymatgen_reduced_composition,
    "E3C013": invoke_pymatgen_atomic_fraction,
    "E3C014": invoke_pymatgen_weight_fraction,
    "E3C015": invoke_pymatgen_weight_to_molar,
}


def invoke(candidate_tool_id: str, params: dict[str, Any]) -> dict[str, Any]:
    adapter = ADAPTERS.get(candidate_tool_id)
    if adapter is None:
        return _failure("UNKNOWN_CANDIDATE_TOOL", f"unknown candidate tool: {candidate_tool_id}")
    return adapter(params)


def invoke_batch2(candidate_tool_id: str, params: dict[str, Any]) -> dict[str, Any]:
    adapter = BATCH2_ADAPTERS.get(candidate_tool_id)
    if adapter is None:
        return _failure("UNKNOWN_OR_BLOCKED_CANDIDATE_TOOL", f"candidate is unknown or blocked: {candidate_tool_id}")
    return adapter(params)
