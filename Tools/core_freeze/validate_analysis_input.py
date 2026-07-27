"""Validate a Core Frozen analysis JSON document."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .analysis_core import load_json, validate_document
except ImportError:  # pragma: no cover - supports direct script execution
    from analysis_core import load_json, validate_document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors = validate_document(load_json(args.input))
    result = {
        "valid": not errors,
        "error_count": len(errors),
        "errors": errors,
        "input": str(args.input.resolve()),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
