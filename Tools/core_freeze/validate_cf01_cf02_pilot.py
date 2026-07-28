"""Validate prepared and human-completed CF-01/CF-02 pilot artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACKAGE = Path(__file__).resolve().parent / "pilot_v1"

CORE_FIELDS = {
    "evidence_requirement": {"none", "optional", "required"},
    "answerability": {
        "answerable",
        "ambiguous_request",
        "missing_task_information",
    },
    "information_status": {
        "sufficient",
        "missing_execution_input",
        "ambiguous_execution_input",
    },
    "capability_status": {"available", "unavailable", "uncertain"},
    "risk_status": {"normal", "review_required"},
}
SET_FIELDS = ("allowed_actions", "boundary_flags")
ALLOWED_ACTIONS = {"answer", "call", "clarify", "refuse", "escalate"}
ANNOTATION_CONFIDENCE = {"high", "medium", "low"}
BOUNDARY_FLAGS = {
    "missing_object",
    "missing_parameter",
    "missing_task_info",
    "missing_execution_info",
    "ambiguous_material",
    "ambiguous_phase",
    "ambiguous_condition",
    "capability_unavailable",
    "tool_unavailable",
    "out_of_domain",
    "unsupported_system",
    "unsupported_phase",
    "unsupported_database",
    "high_risk",
    "permission_required",
    "conflicting_requirements",
}
REQUIRED_POOL_SIZES = (17, 50, 100, 120)
REQUIRED_REPEATS = ("A", "B", "C", "D", "E")
REQUIRED_CONTROLLED = (
    ("none", 0),
    ("lexical", 4),
    ("lexical", 8),
    ("functional_overlap", 4),
    ("functional_overlap", 8),
)


class PilotValidationError(ValueError):
    """Raised when a pilot artifact violates the frozen contract."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PilotValidationError(f"missing required file: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise PilotValidationError(f"invalid JSON in {path.name}: {exc}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_unique(rows: list[dict[str, Any]], field: str, label: str) -> list[str]:
    values = [row.get(field) for row in rows]
    if any(not isinstance(value, str) or not value for value in values):
        raise PilotValidationError(f"{label} contains an empty {field}")
    duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
    if duplicates:
        raise PilotValidationError(f"{label} has duplicate {field}: {duplicates}")
    return values


def validate_track_a_prepared(package_dir: Path) -> dict[str, Any]:
    tasks_payload = load_json(package_dir / "track_a_tasks.json")
    manifest = load_json(package_dir / "track_a_selection_manifest.json")
    tasks = tasks_payload.get("tasks", [])
    selections = manifest.get("tasks", [])
    if len(tasks) < 20 or tasks_payload.get("task_count") != len(tasks):
        raise PilotValidationError("Track A must contain at least 20 frozen tasks")
    task_ids = ensure_unique(tasks, "task_id", "Track A tasks")
    selection_ids = ensure_unique(selections, "task_id", "Track A manifest")
    if set(task_ids) != set(selection_ids):
        raise PilotValidationError("Track A task and selection-manifest IDs differ")

    allowed_task_keys = {"task_id", "question", "context"}
    for task in tasks:
        leaked = set(task) - allowed_task_keys
        if leaked:
            raise PilotValidationError(
                f"annotator-facing Track A task {task['task_id']} leaks {sorted(leaked)}"
            )
        if not isinstance(task.get("question"), str) or not task["question"].strip():
            raise PilotValidationError(f"Track A task {task['task_id']} has no question")

    coverage: dict[str, set[str]] = defaultdict(set)
    group_counts: Counter[str] = Counter()
    for row in selections:
        anticipated = row.get("anticipated_coverage")
        if not isinstance(anticipated, dict):
            raise PilotValidationError(
                f"Track A selection {row['task_id']} has no anticipated coverage"
            )
        for field, allowed in CORE_FIELDS.items():
            values = anticipated.get(field)
            if not isinstance(values, list) or not values:
                raise PilotValidationError(
                    f"Track A selection {row['task_id']} lacks coverage for {field}"
                )
            unexpected = set(values) - allowed
            if unexpected:
                raise PilotValidationError(
                    f"Track A selection {row['task_id']} has invalid {field}: "
                    f"{sorted(unexpected)}"
                )
            coverage[field].update(values)
        group = row.get("minimal_difference_group")
        if group:
            group_counts[group] += 1

    missing_coverage = {
        field: sorted(allowed - coverage[field])
        for field, allowed in CORE_FIELDS.items()
        if allowed - coverage[field]
    }
    if missing_coverage:
        raise PilotValidationError(
            f"Track A anticipated coverage is incomplete: {missing_coverage}"
        )
    qualifying_groups = sorted(group for group, count in group_counts.items() if count >= 2)
    if not qualifying_groups:
        raise PilotValidationError("Track A has no minimal-difference group")

    for annotator_id in ("a", "b"):
        payload = load_json(package_dir / f"track_a_annotator_{annotator_id}.json")
        rows = payload.get("annotations", [])
        annotation_ids = ensure_unique(
            rows, "task_id", f"Track A annotator {annotator_id.upper()}"
        )
        if set(annotation_ids) != set(task_ids):
            raise PilotValidationError(
                f"Track A annotator {annotator_id.upper()} task IDs differ"
            )
        if payload.get("independence_status") == "not_started":
            for row in rows:
                filled = [
                    field for field, value in row.items() if field != "task_id" and value
                ]
                if filled:
                    raise PilotValidationError(
                        f"not-started annotation {row['task_id']} contains {filled}"
                    )

    source = manifest.get("source_dataset", {})
    source_path = PROJECT_ROOT / source.get("path", "")
    if not source_path.is_file():
        raise PilotValidationError("Track A source dataset does not exist")
    if sha256_file(source_path) != source.get("sha256"):
        raise PilotValidationError("Track A source dataset hash has changed")

    return {
        "task_count": len(tasks),
        "coverage": {field: sorted(values) for field, values in coverage.items()},
        "minimal_difference_groups": qualifying_groups,
        "annotator_templates": "present_and_isolated",
        "source_hash": "matched",
    }


def validate_track_b_prepared(package_dir: Path) -> dict[str, Any]:
    tasks_payload = load_json(package_dir / "track_b_tasks.json")
    hints_payload = load_json(package_dir / "track_b_legacy_review_hints.json")
    inventory = load_json(package_dir / "track_b_tool_inventory_snapshot.json")
    construction = load_json(package_dir / "track_b_construction.json")
    status = load_json(package_dir / "pilot_status.json")

    tasks = tasks_payload.get("tasks", [])
    if len(tasks) < 20 or tasks_payload.get("task_count") != len(tasks):
        raise PilotValidationError("Track B must contain at least 20 frozen tasks")
    task_ids = ensure_unique(tasks, "task_id", "Track B tasks")
    hint_ids = ensure_unique(
        hints_payload.get("tasks", []), "task_id", "Track B legacy hints"
    )
    construction_ids = ensure_unique(
        construction.get("tasks", []), "task_id", "Track B construction"
    )
    if set(task_ids) != set(hint_ids) or set(task_ids) != set(construction_ids):
        raise PilotValidationError("Track B task, hint, and construction IDs differ")

    for task in tasks:
        allowed_task_keys = {"task_id", "question", "provided_inputs"}
        leaked = set(task) - allowed_task_keys
        if leaked:
            raise PilotValidationError(
                f"annotator-facing Track B task {task['task_id']} leaks {sorted(leaked)}"
            )
        if not task.get("question"):
            raise PilotValidationError(f"Track B task {task['task_id']} has no question")

    tool_rows = inventory.get("tools", [])
    tool_ids = ensure_unique(tool_rows, "tool_id", "Track B tool inventory")
    if inventory.get("implemented_tool_count") != len(tool_rows):
        raise PilotValidationError("Track B implemented tool count is inconsistent")
    if inventory.get("cf05_accepted_tool_count") != 0:
        raise PilotValidationError(
            "preparation snapshot must not claim CF-05 acceptance without audit"
        )

    if tuple(construction.get("required_pool_sizes", [])) != REQUIRED_POOL_SIZES:
        raise PilotValidationError("Track B required pool sizes changed")
    if tuple(construction.get("required_pool_repeats", [])) != REQUIRED_REPEATS:
        raise PilotValidationError("Track B required A-E repeats changed")
    actual_conditions = {
        (row.get("near_neighbor_type"), row.get("near_neighbor_count"))
        for row in construction.get("required_controlled_conditions", [])
    }
    if actual_conditions != set(REQUIRED_CONTROLLED):
        raise PilotValidationError("Track B controlled-dose conditions changed")

    cf02 = status.get("cf02", {})
    expected_gap = max(0, 120 - len(tool_rows))
    if cf02.get("implemented_tool_count") != len(tool_rows):
        raise PilotValidationError("CF-02 status tool count is inconsistent")
    if cf02.get("tool_count_gap") != expected_gap:
        raise PilotValidationError("CF-02 status tool-count gap is inconsistent")
    if len(tool_rows) < 120 and cf02.get("pool_construction") != "blocked":
        raise PilotValidationError(
            "CF-02 must remain blocked while fewer than 120 tools are implemented"
        )

    hint_tools = {
        tool_id
        for row in hints_payload.get("tasks", [])
        for tool_id in row.get("legacy_expected_tools_unverified", [])
    }
    missing_hint_tools = sorted(hint_tools - set(tool_ids))
    if missing_hint_tools:
        raise PilotValidationError(
            f"legacy routing hints reference absent tools: {missing_hint_tools}"
        )
    uncovered_tools = sorted(set(tool_ids) - hint_tools)
    if uncovered_tools:
        raise PilotValidationError(
            f"Track B pilot does not cover implemented tools: {uncovered_tools}"
        )

    return {
        "task_count": len(tasks),
        "implemented_tool_count": len(tool_rows),
        "cf05_accepted_tool_count": inventory.get("cf05_accepted_tool_count"),
        "required_tool_count": 120,
        "tool_count_gap": expected_gap,
        "pool_construction": cf02.get("pool_construction"),
        "implemented_tool_coverage": f"{len(tool_ids)}_of_{len(tool_ids)}",
        "legacy_hints": "separated_from_gold",
    }


def cohen_kappa(left: list[str], right: list[str]) -> float:
    if len(left) != len(right) or not left:
        raise PilotValidationError("Cohen kappa requires equal non-empty vectors")
    total = len(left)
    observed = sum(a == b for a, b in zip(left, right, strict=True)) / total
    left_counts = Counter(left)
    right_counts = Counter(right)
    expected = sum(
        (left_counts[label] / total) * (right_counts[label] / total)
        for label in set(left_counts) | set(right_counts)
    )
    if math.isclose(expected, 1.0):
        return 1.0 if math.isclose(observed, 1.0) else 0.0
    return (observed - expected) / (1.0 - expected)


def jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    union = left_set | right_set
    return len(left_set & right_set) / len(union) if union else 1.0


def load_completed_annotations(
    package_dir: Path, annotator_id: str, task_ids: set[str]
) -> dict[str, dict[str, Any]]:
    payload = load_json(package_dir / f"track_a_annotator_{annotator_id}.json")
    if payload.get("independence_status") != "completed":
        raise PilotValidationError(
            f"Track A annotator {annotator_id.upper()} is not completed"
        )
    if not payload.get("annotator_name") or not payload.get("annotator_role"):
        raise PilotValidationError(
            f"Track A annotator {annotator_id.upper()} identity is incomplete"
        )
    try:
        started_at = datetime.fromisoformat(payload["started_at"])
        completed_at = datetime.fromisoformat(payload["completed_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PilotValidationError(
            f"Track A annotator {annotator_id.upper()} timestamps are invalid"
        ) from exc
    if started_at.tzinfo is None or completed_at.tzinfo is None:
        raise PilotValidationError(
            f"Track A annotator {annotator_id.upper()} timestamps need timezones"
        )
    if completed_at < started_at:
        raise PilotValidationError(
            f"Track A annotator {annotator_id.upper()} completed before starting"
        )
    rows = payload.get("annotations", [])
    ids = ensure_unique(rows, "task_id", f"Track A annotator {annotator_id.upper()}")
    if set(ids) != task_ids:
        raise PilotValidationError(
            f"Track A annotator {annotator_id.upper()} task IDs differ"
        )
    result = {row["task_id"]: row for row in rows}
    for task_id, row in result.items():
        for field, allowed in CORE_FIELDS.items():
            if row.get(field) not in allowed:
                raise PilotValidationError(
                    f"{annotator_id.upper()} {task_id} has invalid {field}"
                )
        actions = row.get("allowed_actions")
        if not isinstance(actions, list) or not actions:
            raise PilotValidationError(
                f"{annotator_id.upper()} {task_id} has no allowed_actions"
            )
        unexpected_actions = set(actions) - ALLOWED_ACTIONS
        if unexpected_actions:
            raise PilotValidationError(
                f"{annotator_id.upper()} {task_id} has invalid actions "
                f"{sorted(unexpected_actions)}"
            )
        if not isinstance(row.get("boundary_flags"), list):
            raise PilotValidationError(
                f"{annotator_id.upper()} {task_id} boundary_flags is not a list"
            )
        unexpected_flags = set(row["boundary_flags"]) - BOUNDARY_FLAGS
        if unexpected_flags:
            raise PilotValidationError(
                f"{annotator_id.upper()} {task_id} has invalid boundary flags "
                f"{sorted(unexpected_flags)}"
            )
        for list_field in ("required_inputs", "missing_inputs"):
            if not isinstance(row.get(list_field), list):
                raise PilotValidationError(
                    f"{annotator_id.upper()} {task_id} {list_field} is not a list"
                )
        if row.get("annotation_confidence") not in ANNOTATION_CONFIDENCE:
            raise PilotValidationError(
                f"{annotator_id.upper()} {task_id} has invalid annotation_confidence"
            )
        if not isinstance(row.get("action_reason"), str) or not row["action_reason"].strip():
            raise PilotValidationError(
                f"{annotator_id.upper()} {task_id} has no action_reason"
            )
    return result


def score_track_a(package_dir: Path) -> dict[str, Any]:
    task_payload = load_json(package_dir / "track_a_tasks.json")
    task_ids = {row["task_id"] for row in task_payload.get("tasks", [])}
    annotator_a = load_json(package_dir / "track_a_annotator_a.json")
    annotator_b = load_json(package_dir / "track_a_annotator_b.json")
    if (
        annotator_a.get("annotator_name")
        and annotator_a.get("annotator_name") == annotator_b.get("annotator_name")
    ):
        raise PilotValidationError("Track A annotators A and B must be different people")
    left = load_completed_annotations(package_dir, "a", task_ids)
    right = load_completed_annotations(package_dir, "b", task_ids)
    ordered = sorted(task_ids)

    core_metrics: dict[str, dict[str, float | bool]] = {}
    for field in CORE_FIELDS:
        left_values = [left[task_id][field] for task_id in ordered]
        right_values = [right[task_id][field] for task_id in ordered]
        raw = sum(
            a == b for a, b in zip(left_values, right_values, strict=True)
        ) / len(ordered)
        kappa = cohen_kappa(left_values, right_values)
        core_metrics[field] = {
            "raw_agreement": raw,
            "cohen_kappa": kappa,
            "passes_kappa_0_75": kappa >= 0.75,
            "passes_raw_agreement_0_70": raw >= 0.70,
        }

    set_metrics: dict[str, dict[str, float | bool]] = {}
    for field in SET_FIELDS:
        values = [
            jaccard(left[task_id][field], right[task_id][field])
            for task_id in ordered
        ]
        mean_value = sum(values) / len(values)
        set_metrics[field] = {
            "mean_jaccard": mean_value,
            "passes_mean_jaccard_0_80": mean_value >= 0.80,
        }

    disagreements = [
        {
            "task_id": task_id,
            "different_core_fields": [
                field
                for field in CORE_FIELDS
                if left[task_id][field] != right[task_id][field]
            ],
            "different_set_fields": [
                field
                for field in SET_FIELDS
                if set(left[task_id][field]) != set(right[task_id][field])
            ],
        }
        for task_id in ordered
        if any(left[task_id][field] != right[task_id][field] for field in CORE_FIELDS)
        or any(
            set(left[task_id][field]) != set(right[task_id][field])
            for field in SET_FIELDS
        )
    ]
    passes = all(
        metric["passes_kappa_0_75"] and metric["passes_raw_agreement_0_70"]
        for metric in core_metrics.values()
    ) and all(
        metric["passes_mean_jaccard_0_80"] for metric in set_metrics.values()
    )
    return {
        "task_count": len(ordered),
        "core_single_label_metrics": core_metrics,
        "set_field_metrics": set_metrics,
        "disagreement_count": len(disagreements),
        "disagreements": disagreements,
        "cf03_candidate_thresholds_passed": passes,
        "note": "Metrics are computed before adjudication.",
    }


def validate_constructed_track_b(package_dir: Path) -> dict[str, Any]:
    construction = load_json(package_dir / "track_b_construction.json")
    inventory = load_json(package_dir / "track_b_tool_inventory_snapshot.json")
    known_tools = {row["tool_id"] for row in inventory.get("tools", [])}
    if len(known_tools) < 120:
        raise PilotValidationError(
            "Track B cannot be constructed with fewer than 120 audited inventory rows"
        )
    accepted_count = inventory.get("cf05_accepted_tool_count")
    if not isinstance(accepted_count, int) or accepted_count < 120 or any(
        row.get("cf05_audit_status") != "accepted"
        for row in inventory.get("tools", [])
    ):
        raise PilotValidationError(
            "Track B construction requires at least 120 CF-05 accepted tools"
        )
    if construction.get("construction_status") != "completed":
        raise PilotValidationError("Track B construction_status is not completed")

    required_keys = {
        ("controlled_dose", neighbor_type, count, size, repeat)
        for neighbor_type, count in REQUIRED_CONTROLLED
        for size in REQUIRED_POOL_SIZES
        for repeat in REQUIRED_REPEATS
    }
    required_keys |= {
        ("mixed_realistic", "mixed", None, size, repeat)
        for size in REQUIRED_POOL_SIZES
        for repeat in REQUIRED_REPEATS
    }
    checked_records = 0
    for task in construction.get("tasks", []):
        task_id = task["task_id"]
        reviews = [task.get("review_a", {}), task.get("review_b", {})]
        reviewers = [review.get("reviewer") for review in reviews]
        if any(not isinstance(reviewer, str) or not reviewer for reviewer in reviewers):
            raise PilotValidationError(f"{task_id} lacks two named independent reviewers")
        if reviewers[0] == reviewers[1]:
            raise PilotValidationError(f"{task_id} reviewers are not independent")
        for review in reviews:
            if (
                not review.get("reviewer_role")
                or not review.get("completed_at")
                or not review.get("acceptable_tools")
                or not isinstance(review.get("unacceptable_near_neighbors"), list)
                or not review.get("routing_reason")
                or not isinstance(review.get("similarity_ratings"), list)
            ):
                raise PilotValidationError(
                    f"{task_id} has an incomplete independent routing review"
                )
        gold = task.get("adjudicated_gold", {})
        acceptable = set(gold.get("acceptable_tools") or [])
        if not acceptable:
            raise PilotValidationError(f"{task_id} has no adjudicated acceptable tools")
        if not acceptable <= known_tools:
            raise PilotValidationError(f"{task_id} acceptable tools are absent")
        if (
            not gold.get("adjudicator")
            or not gold.get("adjudicated_at")
            or not isinstance(gold.get("unacceptable_near_neighbors"), list)
            or not gold.get("routing_reason")
        ):
            raise PilotValidationError(f"{task_id} has incomplete adjudicated gold")

        near_neighbor_ids = {
            row.get("tool_id") for row in gold["unacceptable_near_neighbors"]
        }
        if None in near_neighbor_ids or not near_neighbor_ids <= known_tools:
            raise PilotValidationError(
                f"{task_id} adjudicated near neighbors contain invalid tools"
            )
        for review in reviews:
            ratings = {
                row.get("tool_id"): row for row in review["similarity_ratings"]
            }
            if not near_neighbor_ids <= set(ratings):
                raise PilotValidationError(
                    f"{task_id} review lacks ratings for adjudicated near neighbors"
                )
            for tool_id in near_neighbor_ids:
                rating = ratings[tool_id]
                components = [
                    rating.get(field)
                    for field in (
                        "same_primary_domain",
                        "same_scientific_goal",
                        "same_input_object",
                        "same_output_quantity",
                        "overlapping_applicability",
                        "name_hard_to_distinguish",
                    )
                ]
                if any(not isinstance(value, bool) for value in components):
                    raise PilotValidationError(
                        f"{task_id}/{tool_id} has invalid similarity components"
                    )
                score = sum(components)
                expected_level = (
                    "low" if score <= 1 else "medium" if score <= 3 else "high"
                )
                if (
                    rating.get("score") != score
                    or rating.get("similarity_level") != expected_level
                ):
                    raise PilotValidationError(
                        f"{task_id}/{tool_id} similarity score is inconsistent"
                    )

        records = task.get("pool_records", [])
        observed: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in records:
            key = (
                row.get("pool_design"),
                row.get("near_neighbor_type"),
                (
                    None
                    if row.get("pool_design") == "mixed_realistic"
                    else row.get("near_neighbor_count")
                ),
                row.get("tool_pool_size"),
                row.get("pool_repeat"),
            )
            if key in observed:
                raise PilotValidationError(f"{task_id} has duplicate pool {key}")
            observed[key] = row
            tool_ids = row.get("tool_ids")
            if not isinstance(tool_ids, list) or len(tool_ids) != row.get(
                "tool_pool_size"
            ):
                raise PilotValidationError(f"{task_id} pool {key} has wrong size")
            if len(set(tool_ids)) != len(tool_ids) or not set(tool_ids) <= known_tools:
                raise PilotValidationError(f"{task_id} pool {key} has invalid tools")
            if not acceptable.intersection(tool_ids):
                raise PilotValidationError(f"{task_id} pool {key} omits all targets")
            neighbor_ids = row.get("near_neighbor_ids", [])
            if not set(neighbor_ids) <= set(tool_ids):
                raise PilotValidationError(
                    f"{task_id} pool {key} has neighbors outside the pool"
                )
            if row.get("pool_design") == "controlled_dose" and len(
                neighbor_ids
            ) != row.get("near_neighbor_count"):
                raise PilotValidationError(
                    f"{task_id} pool {key} has wrong neighbor dose"
                )
        missing = required_keys - set(observed)
        if missing:
            raise PilotValidationError(
                f"{task_id} is missing {len(missing)} required pool records"
            )

        for design, neighbor_type, count in [
            ("controlled_dose", ntype, ncount)
            for ntype, ncount in REQUIRED_CONTROLLED
        ] + [("mixed_realistic", "mixed", None)]:
            for repeat in REQUIRED_REPEATS:
                prior: set[str] = set()
                for size in REQUIRED_POOL_SIZES:
                    row = observed[(design, neighbor_type, count, size, repeat)]
                    current = set(row["tool_ids"])
                    if prior and not prior < current:
                        raise PilotValidationError(
                            f"{task_id} pool is not strictly nested for "
                            f"{design}/{neighbor_type}/{count}/{repeat}"
                        )
                    prior = current
        checked_records += len(required_keys)
    return {
        "task_count": len(construction.get("tasks", [])),
        "required_records_per_task": len(required_keys),
        "checked_pool_records": checked_records,
        "nested_pool_contract": "passed",
    }


def validate_package(package_dir: Path, stage: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "package_dir": str(package_dir.resolve()),
        "stage": stage,
        "cf01_preparation": validate_track_a_prepared(package_dir),
        "cf02_preparation": validate_track_b_prepared(package_dir),
    }
    if stage in {"annotated", "constructed"}:
        result["cf01_agreement"] = score_track_a(package_dir)
    if stage == "constructed":
        result["cf02_construction"] = validate_constructed_track_b(package_dir)
    result["validation_status"] = "passed"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package_dir", type=Path, nargs="?", default=DEFAULT_PACKAGE)
    parser.add_argument(
        "--stage",
        choices=("prepared", "annotated", "constructed"),
        default="prepared",
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = validate_package(args.package_dir.resolve(), args.stage)
    except PilotValidationError as exc:
        print(json.dumps({"validation_status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
