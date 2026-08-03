"""Build the deterministic, nonconfirmatory review after E3 equivalence execution."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("post_equivalence_review_config_v1.json")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validate_binding(binding: dict[str, str]) -> Path:
    path = WORKSPACE / binding["path"]
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256_file(path)
    if actual != binding["sha256"].lower():
        raise ValueError(f"binding hash mismatch for {binding['path']}: {actual}")
    return path


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def build_review(config: dict[str, Any]) -> dict[str, Any]:
    if config.get("external_api_calls_authorized") is not False:
        raise ValueError("post-equivalence review must remain offline")
    if config.get("formal_catalog_admission_allowed") is not False:
        raise ValueError("review cannot admit formal catalog entries")
    if config.get("formal_pool_generation_allowed") is not False:
        raise ValueError("review cannot generate formal pools")
    if config.get("confirmatory_inference_allowed") is not False:
        raise ValueError("review must remain nonconfirmatory")

    bound_paths = {binding["path"]: validate_binding(binding) for binding in config["bindings"]}
    summary = load_json(
        bound_paths[
            "outputs/v11_cf05_e3_equivalence_batch1_r1_20260803/equivalence_candidate_summary.json"
        ]
    )
    cases = load_json(
        bound_paths[
            "outputs/v11_cf05_e3_equivalence_batch1_r1_20260803/equivalence_case_results.json"
        ]
    )
    report = load_json(
        bound_paths[
            "outputs/v11_cf05_e3_equivalence_batch1_r1_20260803/equivalence_run_report.json"
        ]
    )
    source_registry = load_json(
        bound_paths[
            "outputs/v11_cf05_e3_source_candidates_batch1_20260803/source_candidate_registry.json"
        ]
    )
    if report["status"] != "completed_nonconfirmatory_equivalence_evidence":
        raise ValueError("equivalence run is not complete")

    candidates = {row["provisional_candidate_id"]: row for row in summary["candidates"]}
    sources = {row["provisional_candidate_id"]: row for row in source_registry["candidates"]}
    case_rows = {
        (row["provisional_candidate_id"], row["reference_case_id"]): row
        for row in cases["rows"]
    }

    exact_spec = config["exact_equivalent_review"]
    candidate_id = exact_spec["provisional_candidate_id"]
    observed = candidates[candidate_id]
    if observed["equivalence_classification"] != "exact_equivalent_over_frozen_scope":
        raise ValueError("configured exact-equivalent candidate did not pass equivalence")
    if sources[candidate_id]["target_tool_id"] != exact_spec["target_tool_id"]:
        raise ValueError("exact-equivalent target binding mismatch")

    target_source_rows = []
    forbidden = set(exact_spec["forbidden_target_import_roots"])
    forbidden_hits: set[str] = set()
    for source in exact_spec["target_runtime_sources"]:
        path = validate_binding(source)
        imports = sorted(imported_roots(path))
        hits = sorted(set(imports) & forbidden)
        forbidden_hits.update(hits)
        target_source_rows.append(
            {
                "path": source["path"],
                "sha256": source["sha256"],
                "import_roots": imports,
                "forbidden_import_hits": hits,
            }
        )
    implementation_provider_distinct = not forbidden_hits
    acceptable_candidate = bool(
        implementation_provider_distinct
        and observed["may_enter_acceptable_tool_set"]
        and not exact_spec["scientific_function_distinct"]
    )
    independence_review = {
        "review_id": config["review_id"],
        "provisional_candidate_id": candidate_id,
        "target_tool_id": exact_spec["target_tool_id"],
        "candidate_distribution": exact_spec["candidate_distribution"],
        "target_runtime_sources": target_source_rows,
        "implementation_provider_distinct": implementation_provider_distinct,
        "scientific_function_distinct": exact_spec["scientific_function_distinct"],
        "acceptable_tools_candidate_over_frozen_scope": acceptable_candidate,
        "formal_registration_required": exact_spec["formal_registration_required"],
        "formal_acceptable_tools_admission": False,
        "catalog_increment_allowed": False,
        "decision": "implementation_independent_functionally_equivalent_candidate",
    }

    fixture_rows = []
    for selection in config["fixture_selections"]:
        key = (selection["provisional_candidate_id"], selection["reference_case_id"])
        if key not in case_rows:
            raise ValueError(f"missing selected failure row: {key}")
        case = case_rows[key]
        if case["comparison_pass"]:
            raise ValueError(f"fixture must bind an observed mismatch: {key}")
        classification = candidates[key[0]]["equivalence_classification"]
        if classification == "exact_equivalent_over_frozen_scope":
            raise ValueError(f"exact-equivalent candidate cannot become a mismatch fixture: {key}")
        fixture_rows.append(
            {
                **selection,
                "equivalence_classification": classification,
                "case_partition": case["case_partition"],
                "expected_success": case["expected_success"],
                "candidate_success": case["candidate_success"],
                "candidate_output": case["candidate_output"],
                "candidate_error_type": case["candidate_error_type"],
                "comparison_basis": case["comparison_basis"],
                "target_reference_behavior_bound": True,
                "candidate_mismatch_observed": True,
                "fixture_status": "development_fixture_candidate_not_held_out",
                "formal_neighbor_admission": False,
            }
        )

    fixture_package = {
        "review_id": config["review_id"],
        "fixture_count": len(fixture_rows),
        "fixtures": fixture_rows,
        "held_out_fixture_count": 0,
        "formal_neighbor_admission_count": 0,
    }
    review_report = {
        "review_id": config["review_id"],
        "scope": config["scope"],
        "status": "post_equivalence_development_review_complete",
        "exact_equivalent_candidate_count": 1,
        "implementation_independence_pass_count": int(implementation_provider_distinct),
        "acceptable_tools_candidate_count": int(acceptable_candidate),
        "formal_acceptable_tools_admission_count": 0,
        "development_fixture_candidate_count": len(fixture_rows),
        "held_out_fixture_count": 0,
        "formal_neighbor_admission_count": 0,
        "catalog_increment_count": 0,
        "filled_relation_slot_count": 0,
        "remaining_lexical_gap": report["remaining_lexical_gap"],
        "remaining_contract_mismatch_gap": report["remaining_contract_mismatch_gap"],
        "external_api_calls": 0,
        "formal_pool_generation_allowed": False,
        "confirmatory_inference_allowed": False,
        "core_frozen": False,
    }
    return {
        "independence_review": independence_review,
        "fixture_package": fixture_package,
        "report": review_report,
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    result = build_review(config)
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {
        "acceptable_candidate_independence_review.json": result["independence_review"],
        "contract_mismatch_fixture_candidates.json": result["fixture_package"],
        "post_equivalence_review_report.json": result["report"],
        "post_equivalence_review_config_snapshot.json": config,
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    manifest = {
        "review_id": config["review_id"],
        "artifact_count": len(artifacts),
        "artifacts": [
            {
                "filename": filename,
                "sha256": sha256_file(output_dir / filename),
                "bytes": (output_dir / filename).stat().st_size,
            }
            for filename in sorted(artifacts)
        ],
    }
    write_json(output_dir / "artifact_manifest.json", manifest)
    return result["report"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    report = build_outputs(Path(args.output_dir).resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
