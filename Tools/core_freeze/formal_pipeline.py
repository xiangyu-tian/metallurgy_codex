"""Generate the complete frozen H3/H4 CSV and JSON artifact set."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

try:
    from .analysis_core import load_json, require_valid_document, write_json
    from .bootstrap_clusters import cluster_bootstrap
    from .build_paired_contrasts import (
        aggregate_pool_repeats,
        build_h3_pairs,
        build_h4_method_contrasts,
        build_h4_scale_pairs,
        run_repeat_summary,
    )
    from .r_engine import ENGINE_LOCK, check_engine, export_glmm_input, run_glmm
except ImportError:  # pragma: no cover - supports direct script execution
    from analysis_core import load_json, require_valid_document, write_json
    from bootstrap_clusters import cluster_bootstrap
    from build_paired_contrasts import (
        aggregate_pool_repeats,
        build_h3_pairs,
        build_h4_method_contrasts,
        build_h4_scale_pairs,
        run_repeat_summary,
    )
    from r_engine import ENGINE_LOCK, check_engine, export_glmm_input, run_glmm


FORMAL_OUTPUTS = (
    "h3_direct_contrast.csv",
    "h3_baseline_contrasts.csv",
    "h4_scale_stability_mixed.csv",
    "run_repeat_summary.csv",
    "cluster_bootstrap_summary.csv",
    "missingness_audit.csv",
    "h3_glmm_fixed_effects.csv",
    "h3_glmm_planned_contrasts.csv",
    "h3_schema_adjusted_sensitivity_glmm_fixed_effects.csv",
    "h3_schema_adjusted_sensitivity_contrasts.csv",
    "h3_method_interaction_sensitivity_glmm_fixed_effects.csv",
    "h3_method_interaction_sensitivity_contrasts.csv",
    "h4_glmm_fixed_effects.csv",
    "h4_glmm_planned_contrasts.csv",
    "h4_schema_adjusted_sensitivity_glmm_fixed_effects.csv",
    "h4_schema_adjusted_sensitivity_contrasts.csv",
    "model_attempts.csv",
    "engine_metadata.csv",
    "confirmatory_report.json",
    "artifact_manifest.csv",
)


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return value


def write_csv_rows(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    if not fields:
        fields = ["status"]
        rows = [{"status": "no_rows"}]
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in fields})


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git_state() -> dict[str, Any]:
    project_root = Path(__file__).resolve().parents[2]
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=project_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "analysis_commit": (
            commit.stdout.strip() if commit.returncode == 0 else None
        ),
        "tracked_worktree_clean": (
            status.returncode == 0 and not status.stdout.strip()
        ),
    }


def _require_complete_pool_repeats(
    rows: Iterable[dict[str, Any]],
    label: str,
) -> None:
    incomplete = [
        {
            "task_id": row["task_id"],
            "model_run_repeat": row["model_run_repeat"],
            "pool_repeats": row["pool_repeats"],
        }
        for row in rows
        if not row["pool_repeats_complete"]
    ]
    if incomplete:
        raise ValueError(f"{label} has incomplete A-E pool repeats: {incomplete}")


def _bootstrap_row(
    label: str,
    rows: list[dict[str, Any]],
    effect_field: str,
    *,
    n_resamples: int,
    seed: int,
) -> dict[str, Any]:
    result = cluster_bootstrap(
        rows,
        effect_field,
        n_resamples=n_resamples,
        seed=seed,
    )
    return {
        "contrast": label,
        "effect_field": effect_field,
        "estimate": result["estimate"],
        "cluster_count": result["cluster_count"],
        "n_resamples": result["n_resamples"],
        "seed": result["seed"],
        "ci_level": result["confidence_interval"]["level"],
        "ci_lower": result["confidence_interval"]["lower"],
        "ci_upper": result["confidence_interval"]["upper"],
    }


def _merge_r_outputs(output_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    metadata: list[dict[str, Any]] = []
    model_prefixes = {
        "h3": (
            "h3",
            "h3_schema_adjusted_sensitivity",
            "h3_method_interaction_sensitivity",
        ),
        "h4": (
            "h4",
            "h4_schema_adjusted_sensitivity",
        ),
    }
    contrast_files = {
        "h3": (
            "h3_glmm_planned_contrasts.csv",
            "h3_schema_adjusted_sensitivity_contrasts.csv",
            "h3_method_interaction_sensitivity_contrasts.csv",
        ),
        "h4": (
            "h4_glmm_planned_contrasts.csv",
            "h4_schema_adjusted_sensitivity_contrasts.csv",
        ),
    }
    for hypothesis, prefixes in model_prefixes.items():
        hypothesis_dir = output_dir / hypothesis
        for row in read_csv_rows(
            hypothesis_dir / f"{hypothesis}_engine_metadata.csv"
        ):
            metadata.append({"hypothesis": hypothesis.upper(), **row})
        standardization = f"{hypothesis}_standardization.csv"
        (output_dir / standardization).write_bytes(
            (hypothesis_dir / standardization).read_bytes()
        )
        for prefix in prefixes:
            for row in read_csv_rows(
                hypothesis_dir / f"{prefix}_model_attempts.csv"
            ):
                attempts.append(
                    {
                        "hypothesis": hypothesis.upper(),
                        "analysis_model": prefix,
                        **row,
                    }
                )
            for filename in (
                f"{prefix}_glmm_fixed_effects.csv",
                f"{prefix}_glmm_random_effects.csv",
            ):
                source = hypothesis_dir / filename
                destination = output_dir / filename
                destination.write_bytes(source.read_bytes())
        for filename in contrast_files[hypothesis]:
            source = hypothesis_dir / filename
            destination = output_dir / filename
            destination.write_bytes(source.read_bytes())
    return attempts, metadata


def _missingness_rows(
    records: Iterable[dict[str, Any]],
    h3_pairs: dict[str, Any],
    h4_pairs: dict[str, Any],
    h4_methods: dict[str, Any],
) -> list[dict[str, Any]]:
    execution_counts = Counter(
        (
            record["request_status"],
            record["execution_status"] or "not_applicable",
        )
        for record in records
    )
    rows = [
        {
            "hypothesis": "ALL",
            "category": "execution_status",
            "count": count,
            "detail": {
                "request_status": request_status,
                "execution_status": execution_status,
            },
        }
        for (request_status, execution_status), count in sorted(
            execution_counts.items()
        )
    ]
    for hypothesis, category, entries in (
        ("H3", "missing_pair", h3_pairs["missing_pairs"]),
        ("H3", "duplicate_cell", h3_pairs["duplicate_cells"]),
        ("H4", "missing_scale_pair", h4_pairs["missing_pairs"]),
        ("H4", "duplicate_cell", h4_pairs["duplicate_cells"]),
        ("H4", "missing_method_pair", h4_methods["missing_pairs"]),
    ):
        rows.extend(
            {
                "hypothesis": hypothesis,
                "category": category,
                "count": 1,
                "detail": entry,
            }
            for entry in entries
        )
    return rows


def run_formal_pipeline(
    document: dict[str, Any],
    output_dir: str | Path,
    *,
    n_resamples: int = 2000,
    seed: int = 20260727,
    glmm_timeout: int = 300,
    input_hash: str | None = None,
) -> dict[str, Any]:
    records = require_valid_document(document)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    h3 = build_h3_pairs(records)
    h4 = build_h4_scale_pairs(records)
    h4_methods = build_h4_method_contrasts(h4["scale_contrasts"])
    if h3["duplicate_cells"] or h4["duplicate_cells"]:
        raise ValueError("duplicate confirmatory cells must be resolved before GLMM")
    write_csv_rows(output / "h3_direct_contrast.csv", h3["direct_contrasts"])
    write_csv_rows(
        output / "h3_baseline_contrasts.csv",
        h3["baseline_contrasts"],
    )
    write_csv_rows(
        output / "h4_scale_stability_mixed.csv",
        h4["scale_contrasts"],
    )

    h3_aggregated = aggregate_pool_repeats(h3["direct_contrasts"], "d_h3")
    _require_complete_pool_repeats(h3_aggregated, "H3")
    h4_aggregated_by_method: dict[str, list[dict[str, Any]]] = {}
    for method in sorted({row["method"] for row in h4["scale_contrasts"]}):
        method_rows = [
            row for row in h4["scale_contrasts"] if row["method"] == method
        ]
        aggregated = aggregate_pool_repeats(
            method_rows,
            "d_h4",
            extra_group_fields=("method",),
        )
        _require_complete_pool_repeats(aggregated, f"H4/{method}")
        h4_aggregated_by_method[method] = aggregated

    run_summaries = [
        {
            "hypothesis": "H3",
            "contrast": "functional_overlap_8_minus_lexical_8",
            **row,
        }
        for row in run_repeat_summary(h3_aggregated, "d_h3")
    ]
    for method, aggregated in h4_aggregated_by_method.items():
        run_summaries.extend(
            {
                "hypothesis": "H4",
                "contrast": "accuracy_120_minus_17",
                "method": method,
                **row,
            }
            for row in run_repeat_summary(aggregated, "d_h4")
        )
    write_csv_rows(output / "run_repeat_summary.csv", run_summaries)

    bootstrap_rows = [
        _bootstrap_row(
            "H3:functional_overlap_8_minus_lexical_8",
            h3_aggregated,
            "d_h3",
            n_resamples=n_resamples,
            seed=seed,
        )
    ]
    for index, (method, aggregated) in enumerate(
        sorted(h4_aggregated_by_method.items())
    ):
        bootstrap_rows.append(
            _bootstrap_row(
                f"H4:{method}:accuracy_120_minus_17",
                aggregated,
                "d_h4",
                n_resamples=n_resamples,
                seed=seed + index + 1,
            )
        )
    for index, baseline in enumerate(("full_schema", "lexical_top5", "dense_top5")):
        method_rows = [
            row
            for row in h4_methods["method_contrasts"]
            if row["baseline_method"] == baseline
        ]
        aggregated = aggregate_pool_repeats(
            method_rows,
            "h4_method_difference",
            extra_group_fields=("baseline_method",),
        )
        _require_complete_pool_repeats(aggregated, f"H4/hierarchical_vs_{baseline}")
        bootstrap_rows.append(
            _bootstrap_row(
                f"H4:hierarchical_vs_{baseline}",
                aggregated,
                "h4_method_difference",
                n_resamples=n_resamples,
                seed=seed + 10 + index,
            )
        )
    write_csv_rows(output / "cluster_bootstrap_summary.csv", bootstrap_rows)

    missingness = _missingness_rows(records, h3, h4, h4_methods)
    write_csv_rows(output / "missingness_audit.csv", missingness)

    versions = check_engine()
    h3_input = export_glmm_input(records, "h3", output / "h3_glmm_input.csv")
    h4_input = export_glmm_input(records, "h4", output / "h4_glmm_input.csv")
    h3_glmm = run_glmm(
        "h3",
        h3_input,
        output / "h3",
        timeout=glmm_timeout,
    )
    h4_glmm = run_glmm(
        "h4",
        h4_input,
        output / "h4",
        timeout=glmm_timeout,
    )
    attempts, metadata = _merge_r_outputs(output)
    write_csv_rows(output / "model_attempts.csv", attempts)
    write_csv_rows(output / "engine_metadata.csv", metadata)

    h4_planned = read_csv_rows(output / "h4_glmm_planned_contrasts.csv")
    support_values = {
        row["support_classification"] for row in h4_planned
    }
    if len(support_values) != 1:
        raise ValueError("H4 support classification is inconsistent across contrasts")
    repository_state = _git_state()
    report = {
        "report_version": "1.0-rc1.1",
        "protocol_version": document["metadata"]["protocol_version"],
        "dataset_version": document["metadata"]["dataset_version"],
        "input_hash": input_hash,
        "analysis_commit": repository_state["analysis_commit"],
        "tracked_worktree_clean": repository_state["tracked_worktree_clean"],
        "r_engine_lock_hash": _sha256(ENGINE_LOCK),
        "generated_at": datetime.now().astimezone().isoformat(),
        "engine": {
            "status": "frozen",
            "versions": versions,
            "specification": "glmm_engine_spec_v1.0-rc1.1.md",
        },
        "formal_models": {
            "H3": h3_glmm,
            "H4": h4_glmm,
        },
        "estimands": {
            "primary": {
                "effect": "total_method_effect",
                "schema_token_count_adjusted": False,
                "h3_interpretation": "equal-weighted average interference effect across four methods",
            },
            "sensitivity": {
                "schema_token_count_adjusted": True,
                "h3_method_by_neighbor_interaction": True,
                "changes_primary_support_classification": False,
            },
        },
        "h4_support_classification": next(iter(support_values)),
        "artifact_files": list(FORMAL_OUTPUTS),
        "missingness_record_count": len(missingness),
        "deviations": [],
        "cf11_status": "in_progress",
        "cf11_components": {
            "design_specification": "passed",
            "engine_implementation": "passed",
            "synthetic_integration": "passed",
            "real_candidate_dry_run": "pending",
            "statistical_review": "pending",
            "report_review": "pending",
            "approval": "pending",
            "overall": "in_progress",
        },
        "cf11_open_items": [
            "real_candidate_data_dry_run",
            "statistics_reviewer_approval",
            "report_template_approval",
        ],
    }
    write_json(output / "confirmatory_report.json", report)
    manifest_rows = [
        {
            "filename": filename,
            "sha256": _sha256(output / filename),
        }
        for filename in FORMAL_OUTPUTS
        if filename != "artifact_manifest.csv"
    ]
    write_csv_rows(output / "artifact_manifest.csv", manifest_rows)
    missing_outputs = [
        filename for filename in FORMAL_OUTPUTS if not (output / filename).is_file()
    ]
    if missing_outputs:
        raise RuntimeError(f"formal pipeline did not create: {missing_outputs}")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--n-resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260727)
    parser.add_argument("--glmm-timeout", type=int, default=300)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_hash = hashlib.sha256(args.input.read_bytes()).hexdigest()
    report = run_formal_pipeline(
        load_json(args.input),
        args.output_dir,
        n_resamples=args.n_resamples,
        seed=args.seed,
        glmm_timeout=args.glmm_timeout,
        input_hash=input_hash,
    )
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir.resolve()),
                "cf11_status": report["cf11_status"],
                "h4_support_classification": report[
                    "h4_support_classification"
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
