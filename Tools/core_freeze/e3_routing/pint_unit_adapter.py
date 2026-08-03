"""Frozen-scope Pint adapter for the A001 acceptable-tool candidate."""

from __future__ import annotations

import math
from typing import Any


PAIR_CATEGORIES = {
    ("kg", "g"): "质量",
    ("t", "kg"): "质量",
    ("m", "mm"): "长度",
    ("MPa", "Pa"): "压强",
    ("atm", "Pa"): "压强",
    ("kJ", "J"): "能量",
    ("°C", "K"): "温度",
    ("°F", "°C"): "温度",
}
UNIT_ALIASES = {"°C": "degC", "°F": "degF"}


def _failure(code: str, message: str) -> dict[str, Any]:
    return {"success": False, "result": None, "error_code": code, "error": message}


def invoke(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        return _failure("INVALID_INPUT", "params must be an object")
    if set(params) != {"value", "source_unit", "target_unit"}:
        return _failure("INVALID_INPUT", "exactly value, source_unit and target_unit are required")
    value = params["value"]
    source = params["source_unit"]
    target = params["target_unit"]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return _failure("INVALID_INPUT", "value must be a finite number")
    if not isinstance(source, str) or not isinstance(target, str):
        return _failure("INVALID_INPUT", "unit symbols must be strings")
    pair = (source, target)
    if pair not in PAIR_CATEGORIES:
        return _failure("UNSUPPORTED_PAIR", f"unit pair is outside frozen scope: {source} -> {target}")
    try:
        import pint

        registry = pint.UnitRegistry()
        source_pint = UNIT_ALIASES.get(source, source)
        target_pint = UNIT_ALIASES.get(target, target)
        converted = registry.Quantity(float(value), source_pint).to(target_pint)
        zero = registry.Quantity(0.0, source_pint).to(target_pint).magnitude
        one = registry.Quantity(1.0, source_pint).to(target_pint).magnitude
        return {
            "success": True,
            "result": {
                "value": float(converted.magnitude),
                "source_unit": source,
                "target_unit": target,
                "conversion_factor": float(one - zero),
                "conversion_offset": float(zero),
                "category": PAIR_CATEGORIES[pair],
            },
            "error_code": None,
            "error": None,
        }
    except Exception as exc:
        name = type(exc).__name__
        if name == "UndefinedUnitError":
            code = "INVALID_UNIT"
        elif name == "DimensionalityError":
            code = "DIMENSION_MISMATCH"
        else:
            code = "EXECUTION_ERROR"
        return _failure(code, f"{name}: {str(exc)[:240]}")
