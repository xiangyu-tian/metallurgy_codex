"""Validate and publish an offline, source-bound E3 candidate discovery batch."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


WORKSPACE = Path(__file__).resolve().parents[3]
SOURCE_PATH = Path(__file__).with_name("source_candidate_batch_v1.json")
ALLOWED_TARGETS = {"A001", "A002", "A003", "A004", "B019"}
ALLOWED_NEIGHBOR_TYPES = {"lexical", "contract_mismatch"}
ALLOWED_SOURCE_HOSTS = {
    "pint.readthedocs.io",
    "rdkit.org",
    "www.rdkit.org",
    "pymatgen.org",
    "pycalphad.org",
}


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


def _require_nonempty_text(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


def validate_batch(batch: dict[str, Any]) -> dict[str, Any]:
    policy = batch["policy"]
    required_policy = {
        "candidate_status": "source_bound_candidate_unreviewed",
        "relation_claim_status": "proposed_pending_fixture",
        "independence_status": "pending",
        "count_toward_catalog": False,
        "execution_allowed": False,
        "external_api_calls_authorized": False,
        "formal_pool_generation_allowed": False,
    }
    if policy != required_policy:
        raise ValueError("candidate policy must remain the frozen non-admission policy")

    catalog_path = WORKSPACE / batch["catalog_binding"]["path"]
    if not catalog_path.is_file():
        raise FileNotFoundError(catalog_path)
    catalog_hash = sha256_file(catalog_path)
    if catalog_hash != batch["catalog_binding"]["sha256"]:
        raise ValueError("catalog binding hash mismatch")
    catalog = load_json(catalog_path)
    catalog_aliases = {entry["semantic_alias"] for entry in catalog["entries"]}

    sources = batch["sources"]
    source_ids = [row["source_id"] for row in sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("duplicate source_id")
    for source in sources:
        for field in ("source_id", "title", "locator", "publisher"):
            _require_nonempty_text(source.get(field), f"source.{field}")
        if source.get("source_type") != "primary_documentation":
            raise ValueError("batch 1 accepts primary documentation only")
        parsed = urlparse(source["locator"])
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_SOURCE_HOSTS:
            raise ValueError(f"unapproved source locator: {source['locator']}")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError(f"source locator must not contain credentials/query/fragment: {source['locator']}")

    candidates = batch["candidates"]
    candidate_ids = [row["provisional_candidate_id"] for row in candidates]
    capability_names = [row["capability_name"] for row in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("duplicate provisional_candidate_id")
    if len(capability_names) != len(set(capability_names)):
        raise ValueError("duplicate capability_name")

    known_sources = set(source_ids)
    target_counts: Counter[str] = Counter()
    package_counts: Counter[str] = Counter()
    exact_catalog_alias_collisions: list[dict[str, str]] = []
    for candidate in candidates:
        for field in (
            "provisional_candidate_id",
            "capability_name",
            "package",
            "operation",
            "documented_capability",
            "known_limitation",
            "disqualifier_risk",
        ):
            _require_nonempty_text(candidate.get(field), f"candidate.{field}")
        target = candidate.get("target_tool_id")
        if target not in ALLOWED_TARGETS:
            raise ValueError(f"unsupported target_tool_id: {target}")
        relation_types = set(candidate.get("proposed_neighbor_types", []))
        if not relation_types or not relation_types <= ALLOWED_NEIGHBOR_TYPES:
            raise ValueError(
                "invalid proposed_neighbor_types for "
                f"{candidate['provisional_candidate_id']}"
            )
        referenced_sources = candidate.get("source_ids", [])
        if not referenced_sources or not set(referenced_sources) <= known_sources:
            raise ValueError(f"invalid source binding for {candidate['provisional_candidate_id']}")
        target_counts[target] += 1
        package_counts[candidate["package"]] += 1
        if candidate["capability_name"] in catalog_aliases:
            exact_catalog_alias_collisions.append(
                {
                    "provisional_candidate_id": candidate["provisional_candidate_id"],
                    "capability_name": candidate["capability_name"],
                }
            )

    enriched_candidates = []
    for candidate in candidates:
        enriched_candidates.append(
            {
                **candidate,
                "candidate_status": policy["candidate_status"],
                "relation_claim_status": policy["relation_claim_status"],
                "independence_status": policy["independence_status"],
                "duplicate_screen_status": "exact_alias_precheck_complete_semantic_review_pending",
                "count_toward_catalog": policy["count_toward_catalog"],
                "execution_allowed": policy["execution_allowed"],
            }
        )

    return {
        "registry": {
            "schema_version": batch["schema_version"],
            "batch_id": batch["batch_id"],
            "retrieved_on": batch["retrieved_on"],
            "catalog_binding": batch["catalog_binding"],
            "sources": sources,
            "candidates": enriched_candidates,
        },
        "precheck": {
            "batch_id": batch["batch_id"],
            "status": "source_binding_passed_admission_review_pending",
            "source_count": len(sources),
            "candidate_count": len(candidates),
            "candidate_count_by_target": dict(sorted(target_counts.items())),
            "candidate_count_by_package": dict(sorted(package_counts.items())),
            "exact_catalog_alias_collision_count": len(exact_catalog_alias_collisions),
            "exact_catalog_alias_collisions": exact_catalog_alias_collisions,
            "semantic_duplicate_review_pending_count": len(candidates),
            "independence_review_pending_count": len(candidates),
            "relation_fixture_pending_count": len(candidates),
            "accepted_candidate_count": 0,
            "catalog_increment_count": 0,
            "filled_relation_slot_count": 0,
            "remaining_lexical_gap": 30,
            "remaining_contract_mismatch_gap": 40,
            "external_api_calls": 0,
            "formal_pool_generation_allowed": False,
            "core_frozen": False,
        },
        "source_manifest": {
            "batch_id": batch["batch_id"],
            "retrieved_on": batch["retrieved_on"],
            "source_count": len(sources),
            "sources": [
                {
                    "source_id": source["source_id"],
                    "publisher": source["publisher"],
                    "locator": source["locator"],
                    "source_type": source["source_type"],
                }
                for source in sources
            ],
        },
    }


def build_outputs(output_dir: Path) -> dict[str, Any]:
    batch = load_json(SOURCE_PATH)
    result = validate_batch(batch)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "source_candidate_registry.json": result["registry"],
        "source_manifest.json": result["source_manifest"],
        "candidate_precheck_report.json": result["precheck"],
        "source_candidate_batch_snapshot.json": batch,
    }
    for filename, value in artifacts.items():
        write_json(output_dir / filename, value)
    manifest = {
        "batch_id": batch["batch_id"],
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
    return result["precheck"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    report = build_outputs(Path(args.output_dir).resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
