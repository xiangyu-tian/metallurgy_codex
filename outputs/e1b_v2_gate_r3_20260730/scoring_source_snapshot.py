"""Strict JSON extraction and automatic scoring for E1b structured answers."""

from __future__ import annotations

import json
import math
import re
from typing import Any


_FENCED_JSON_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    flags=re.IGNORECASE | re.DOTALL,
)


def _object_candidates(text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    candidates = []
    covered_until = -1
    for index, char in enumerate(text):
        if char != "{" or index < covered_until:
            continue
        try:
            value, consumed = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        candidates.append(value)
        covered_until = index + consumed
    return candidates


def extract_json_answer(raw_text: Any) -> dict[str, Any]:
    """Extract exactly one JSON object without silently choosing among alternatives."""
    if not isinstance(raw_text, str) or not raw_text.strip():
        return {
            "status": "empty",
            "answer": None,
            "error": "response content is empty",
        }

    text = raw_text.strip()
    try:
        direct = json.loads(text)
    except json.JSONDecodeError:
        direct = None
    if isinstance(direct, dict):
        return {"status": "parsed", "answer": direct, "error": None}
    if direct is not None:
        return {
            "status": "invalid",
            "answer": None,
            "error": "top-level JSON value must be an object",
        }

    fenced = []
    for match in _FENCED_JSON_RE.finditer(text):
        try:
            value = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            fenced.append(value)
    if len(fenced) == 1:
        return {"status": "parsed", "answer": fenced[0], "error": None}
    if len(fenced) > 1:
        return {
            "status": "ambiguous",
            "answer": None,
            "error": "multiple valid fenced JSON objects",
        }

    candidates = _object_candidates(text)
    if len(candidates) == 1:
        return {"status": "parsed", "answer": candidates[0], "error": None}
    if len(candidates) > 1:
        return {
            "status": "ambiguous",
            "answer": None,
            "error": "multiple valid JSON objects",
        }
    return {
        "status": "invalid",
        "answer": None,
        "error": "no valid JSON object found",
    }


def resolve_path(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(path)
        value = value[part]
    return value


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _numeric_pairs(actual: Any, expected: Any) -> list[tuple[float, float]]:
    if _is_number(actual) and _is_number(expected):
        return [(float(actual), float(expected))]
    if isinstance(actual, dict) and isinstance(expected, dict):
        pairs = []
        for key, expected_value in expected.items():
            if key not in actual:
                continue
            pairs.extend(_numeric_pairs(actual[key], expected_value))
        return pairs
    if isinstance(actual, list) and isinstance(expected, list):
        pairs = []
        for actual_value, expected_value in zip(actual, expected):
            pairs.extend(_numeric_pairs(actual_value, expected_value))
        return pairs
    return []


def _strict_equal(actual: Any, expected: Any) -> bool:
    if _is_number(expected):
        return _is_number(actual) and float(actual) == float(expected)
    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and set(actual) == set(expected)
            and all(_strict_equal(actual[key], value) for key, value in expected.items())
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                _strict_equal(actual_value, expected_value)
                for actual_value, expected_value in zip(actual, expected)
            )
        )
    if isinstance(expected, bool):
        return isinstance(actual, bool) and actual is expected
    return type(actual) is type(expected) and actual == expected


def _normalized_error(actual: Any, expected: Any, epsilon: float = 1e-12) -> float | None:
    pairs = _numeric_pairs(actual, expected)
    if not pairs:
        return None
    errors = [
        abs(actual_value - expected_value) / max(abs(expected_value), epsilon)
        for actual_value, expected_value in pairs
    ]
    return sum(errors) / len(errors)


def score_answer(
    parsed_answer: dict[str, Any] | None,
    scoring_rule: dict[str, Any],
) -> dict[str, Any]:
    checks = scoring_rule.get("checks", [])
    check_results = []
    if not isinstance(parsed_answer, dict):
        return {
            "correct": False,
            "normalized_error": None,
            "check_results": [
                {
                    "path": check.get("path"),
                    "passed": False,
                    "error": "answer is not a parsed JSON object",
                }
                for check in checks
            ],
        }

    normalized_errors = []
    for check in checks:
        path = check["path"]
        try:
            actual = resolve_path(parsed_answer, path)
        except KeyError:
            check_results.append(
                {
                    "path": path,
                    "passed": False,
                    "actual": None,
                    "expected": check.get("value"),
                    "error": "missing answer path",
                }
            )
            continue

        expected = check["value"]
        op = check["op"]
        error = None
        if op == "equal":
            passed = _strict_equal(actual, expected)
        elif op == "approx":
            if not _is_number(actual):
                passed = False
                error = "actual value is not a finite number"
            else:
                passed = math.isclose(
                    float(actual),
                    float(expected),
                    rel_tol=float(check.get("rel_tol", 0.0)),
                    abs_tol=float(check.get("abs_tol", 0.0)),
                )
        elif op == "less_equal":
            if not _is_number(actual):
                passed = False
                error = "actual value is not a finite number"
            else:
                passed = float(actual) <= float(expected)
        else:
            passed = False
            error = f"unsupported comparison operator: {op}"

        numeric_error = _normalized_error(actual, expected)
        if numeric_error is not None:
            normalized_errors.append(numeric_error)
        check_results.append(
            {
                "path": path,
                "op": op,
                "passed": passed,
                "actual": actual,
                "expected": expected,
                "abs_tol": check.get("abs_tol"),
                "rel_tol": check.get("rel_tol"),
                "normalized_error": numeric_error,
                "error": error,
            }
        )

    return {
        "correct": bool(check_results)
        and all(row["passed"] for row in check_results),
        "normalized_error": (
            sum(normalized_errors) / len(normalized_errors)
            if normalized_errors
            else None
        ),
        "check_results": check_results,
    }


def parse_and_score(raw_text: Any, scoring_rule: dict[str, Any]) -> dict[str, Any]:
    extraction = extract_json_answer(raw_text)
    score = score_answer(extraction["answer"], scoring_rule)
    return {
        "parse_status": extraction["status"],
        "parse_error": extraction["error"],
        "parsed_answer": extraction["answer"],
        **score,
    }
