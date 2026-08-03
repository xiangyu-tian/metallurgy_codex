"""Callable wrappers for the first E3 nonformal registration candidates."""

from __future__ import annotations

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


ADAPTERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "E3C001": invoke_pint_unit_conversion,
    "E3C002": invoke_pymatgen_formula_parser,
    "E3C003": invoke_rdkit_average_molecular_weight,
    "E3C004": invoke_pymatgen_composition_weight,
    "E3C005": invoke_pymatgen_fractional_composition,
}


def invoke(candidate_tool_id: str, params: dict[str, Any]) -> dict[str, Any]:
    adapter = ADAPTERS.get(candidate_tool_id)
    if adapter is None:
        return _failure("UNKNOWN_CANDIDATE_TOOL", f"unknown candidate tool: {candidate_tool_id}")
    return adapter(params)
