"""Python boundary for the frozen R/lme4 GLMM engine."""

from __future__ import annotations

import csv
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable

try:
    from .analysis_core import H4_METHODS, selection_correct
except ImportError:  # pragma: no cover - supports direct script execution
    from analysis_core import H4_METHODS, selection_correct


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENGINE_SCRIPT = Path(__file__).with_name("glmm_engine.R")
ENGINE_LOCK = Path(__file__).with_name("r_engine_lock.json")
DEFAULT_RSCRIPT = (
    PROJECT_ROOT / ".r-runtime" / "R-4.6.1" / "bin" / "Rscript.exe"
)
DEFAULT_R_LIBRARY = PROJECT_ROOT / ".r-runtime" / "library"
H3_METHODS = tuple(H4_METHODS)
H3_CONDITIONS = {
    ("none", 0),
    ("lexical", 4),
    ("lexical", 8),
    ("functional_overlap", 4),
    ("functional_overlap", 8),
}


class REngineError(RuntimeError):
    """Raised when the frozen R engine is unavailable or rejects a model."""


def engine_paths() -> tuple[Path, Path]:
    rscript = Path(os.environ.get("METALLURGY_RSCRIPT", DEFAULT_RSCRIPT))
    r_library = Path(os.environ.get("METALLURGY_R_LIBRARY", DEFAULT_R_LIBRARY))
    return rscript, r_library


def engine_environment(r_library: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["R_LIBS_USER"] = str(r_library.resolve())
    return environment


def check_engine(timeout: int = 30) -> dict[str, str]:
    rscript, r_library = engine_paths()
    if not rscript.is_file():
        raise REngineError(f"Rscript is not installed at {rscript}")
    if not r_library.is_dir():
        raise REngineError(f"R package library is not installed at {r_library}")
    completed = subprocess.run(
        [str(rscript), str(ENGINE_SCRIPT), "--check"],
        cwd=PROJECT_ROOT,
        env=engine_environment(r_library),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise REngineError(
            f"R engine check failed ({completed.returncode}): "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    versions = {}
    for line in completed.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            versions[key.strip()] = value.strip()
    expected = json.loads(ENGINE_LOCK.read_text(encoding="utf-8"))
    if versions.get("R") != expected["r_version"]:
        raise REngineError("R engine output does not match r_engine_lock.json")
    mismatches = {
        package_name: {
            "expected": expected_version,
            "actual": versions.get(package_name),
        }
        for package_name, expected_version in expected["packages"].items()
        if versions.get(package_name) != expected_version
    }
    if mismatches:
        raise REngineError(
            "R package versions do not match r_engine_lock.json: "
            f"{mismatches}"
        )
    return versions


def _require_formal_fields(record: dict[str, Any], index: int) -> None:
    missing = [
        field
        for field in ("difficulty_score", "schema_token_count")
        if field not in record
    ]
    if missing:
        raise REngineError(
            f"records[{index}] is missing formal GLMM fields: {missing}"
        )


def _observable_records(
    records: Iterable[dict[str, Any]],
    hypothesis: str,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        _require_formal_fields(record, index)
        if hypothesis == "h3":
            include = (
                record["pool_design"] == "controlled_dose"
                and record["tool_pool_size"] == 120
                and (
                    record["near_neighbor_type"],
                    record["near_neighbor_count"],
                )
                in H3_CONDITIONS
            )
        elif hypothesis == "h4":
            include = (
                record["pool_design"] == "mixed_realistic"
                and record["tool_pool_size"] in {17, 50, 100, 120}
            )
        else:
            raise ValueError("hypothesis must be h3 or h4")
        if not include:
            continue
        correctness = selection_correct(record)
        if correctness is None:
            continue
        selected.append({**record, "selection_correct": correctness})
    if not selected:
        raise REngineError(f"{hypothesis.upper()} has no observable formal rows")
    methods = {record["method"] for record in selected}
    if methods != set(H3_METHODS):
        raise REngineError(
            f"{hypothesis.upper()} method set mismatch: "
            f"expected={sorted(H3_METHODS)}, actual={sorted(methods)}"
        )
    return selected


def export_glmm_input(
    records: Iterable[dict[str, Any]],
    hypothesis: str,
    output_path: str | Path,
) -> Path:
    rows = _observable_records(records, hypothesis)
    fields = [
        "task_id",
        "selection_correct",
        "method",
        "minimal_pair_group",
        "target_tool_family",
        "pool_family_id",
        "pool_repeat",
        "model_run_repeat",
        "difficulty_score",
        "schema_token_count",
        "tool_pool_size",
        "near_neighbor_type",
        "near_neighbor_count",
    ]
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            exported = dict(row)
            exported["minimal_pair_group"] = (
                row["minimal_pair_group"] or f"TASK::{row['task_id']}"
            )
            writer.writerow(exported)
    return output


def run_glmm(
    hypothesis: str,
    input_csv: str | Path,
    output_dir: str | Path,
    *,
    timeout: int = 300,
) -> dict[str, Any]:
    versions = check_engine()
    rscript, r_library = engine_paths()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            str(rscript),
            str(ENGINE_SCRIPT),
            hypothesis,
            str(Path(input_csv).resolve()),
            str(output.resolve()),
        ],
        cwd=PROJECT_ROOT,
        env=engine_environment(r_library),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise REngineError(
            f"{hypothesis.upper()} GLMM failed ({completed.returncode}): "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    return {
        "hypothesis": hypothesis.upper(),
        "status": "converged",
        "versions": versions,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "output_dir": str(output.resolve()),
    }
