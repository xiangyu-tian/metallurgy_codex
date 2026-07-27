"""Shared validation and I/O for Core Frozen analysis artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "1.0-rc1.1"
PROTOCOL_VERSION = "1.0-rc3.1"
POOL_REPEATS = ("A", "B", "C", "D", "E")
POOL_SIZES = {17, 50, 100, 120}
POOL_DESIGNS = {
    "controlled_dose",
    "pure_type_exploratory",
    "mixed_realistic",
}
NEIGHBOR_TYPES = {"none", "lexical", "functional_overlap", "mixed"}
REQUEST_STATUSES = {"accepted", "not_accepted"}
EXECUTION_STATUSES = {
    "success",
    "model_failure",
    "provider_failure",
    "timeout",
    "invalid_response",
}
H4_METHODS = (
    "hierarchical",
    "full_schema",
    "lexical_top5",
    "dense_top5",
)

REQUIRED_RECORD_FIELDS = {
    "task_id",
    "minimal_pair_group",
    "target_tool_family",
    "acceptable_tools",
    "tool_pool_id",
    "pool_family_id",
    "pool_repeat",
    "model_run_repeat",
    "method",
    "tool_pool_size",
    "pool_design",
    "near_neighbor_type",
    "near_neighbor_count",
    "selected_tool",
    "end_to_end_correct",
    "request_status",
    "execution_status",
}


class AnalysisValidationError(ValueError):
    """Raised when an analysis document violates the frozen input contract."""

    def __init__(self, errors: Iterable[str]):
        self.errors = list(errors)
        super().__init__("\n".join(self.errors))


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, value: Any) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_record(record: Any, index: int) -> list[str]:
    prefix = f"records[{index}]"
    if not isinstance(record, dict):
        return [f"{prefix}: must be an object"]

    errors: list[str] = []
    missing = sorted(REQUIRED_RECORD_FIELDS - record.keys())
    if missing:
        errors.append(f"{prefix}: missing fields {missing}")
        return errors

    for field in (
        "task_id",
        "target_tool_family",
        "tool_pool_id",
        "pool_family_id",
        "method",
    ):
        if not _non_empty_string(record[field]):
            errors.append(f"{prefix}.{field}: must be a non-empty string")

    minimal_pair_group = record["minimal_pair_group"]
    if minimal_pair_group is not None and not _non_empty_string(minimal_pair_group):
        errors.append(
            f"{prefix}.minimal_pair_group: must be null or a non-empty string"
        )

    acceptable_tools = record["acceptable_tools"]
    if (
        not isinstance(acceptable_tools, list)
        or not acceptable_tools
        or any(not _non_empty_string(item) for item in acceptable_tools)
        or len(set(acceptable_tools)) != len(acceptable_tools)
    ):
        errors.append(
            f"{prefix}.acceptable_tools: must contain unique non-empty strings"
        )

    if not isinstance(record["pool_repeat"], str) or record["pool_repeat"] not in POOL_REPEATS:
        errors.append(f"{prefix}.pool_repeat: must be one of {POOL_REPEATS}")
    if (
        not isinstance(record["model_run_repeat"], int)
        or isinstance(record["model_run_repeat"], bool)
        or record["model_run_repeat"] < 1
    ):
        errors.append(f"{prefix}.model_run_repeat: must be an integer >= 1")
    if (
        not isinstance(record["tool_pool_size"], int)
        or isinstance(record["tool_pool_size"], bool)
        or record["tool_pool_size"] not in POOL_SIZES
    ):
        errors.append(f"{prefix}.tool_pool_size: unsupported size")
    if (
        not isinstance(record["pool_design"], str)
        or record["pool_design"] not in POOL_DESIGNS
    ):
        errors.append(f"{prefix}.pool_design: unsupported design")
    if (
        not isinstance(record["near_neighbor_type"], str)
        or record["near_neighbor_type"] not in NEIGHBOR_TYPES
    ):
        errors.append(f"{prefix}.near_neighbor_type: unsupported type")
    if (
        not isinstance(record["near_neighbor_count"], int)
        or isinstance(record["near_neighbor_count"], bool)
        or record["near_neighbor_count"] < 0
    ):
        errors.append(f"{prefix}.near_neighbor_count: must be an integer >= 0")
    if record["selected_tool"] is not None and not _non_empty_string(
        record["selected_tool"]
    ):
        errors.append(f"{prefix}.selected_tool: must be null or a non-empty string")
    if record["end_to_end_correct"] is not None and not isinstance(
        record["end_to_end_correct"], bool
    ):
        errors.append(f"{prefix}.end_to_end_correct: must be boolean or null")

    request_status = record["request_status"]
    execution_status = record["execution_status"]
    if not isinstance(request_status, str) or request_status not in REQUEST_STATUSES:
        errors.append(f"{prefix}.request_status: unsupported status")
    if (
        execution_status is not None
        and (
            not isinstance(execution_status, str)
            or execution_status not in EXECUTION_STATUSES
        )
    ):
        errors.append(f"{prefix}.execution_status: unsupported status")

    if request_status == "not_accepted":
        if execution_status is not None:
            errors.append(
                f"{prefix}: not_accepted requests require execution_status=null"
            )
        if record["selected_tool"] is not None:
            errors.append(f"{prefix}: not_accepted requests cannot select a tool")
        if record["end_to_end_correct"] is not None:
            errors.append(
                f"{prefix}: not_accepted requests require end_to_end_correct=null"
            )
    elif request_status == "accepted" and execution_status is None:
        errors.append(f"{prefix}: accepted requests require execution_status")

    if (
        isinstance(execution_status, str)
        and execution_status in EXECUTION_STATUSES - {"success"}
        and record["end_to_end_correct"] is True
    ):
        errors.append(
            f"{prefix}: failed execution cannot have end_to_end_correct=true"
        )

    if "difficulty_score" in record and (
        not isinstance(record["difficulty_score"], int)
        or isinstance(record["difficulty_score"], bool)
        or not 0 <= record["difficulty_score"] <= 5
    ):
        errors.append(f"{prefix}.difficulty_score: must be an integer from 0 to 5")
    if "schema_token_count" in record and (
        not isinstance(record["schema_token_count"], int)
        or isinstance(record["schema_token_count"], bool)
        or record["schema_token_count"] < 0
    ):
        errors.append(f"{prefix}.schema_token_count: must be an integer >= 0")

    pool_design = record["pool_design"]
    neighbor_type = record["near_neighbor_type"]
    neighbor_count = record["near_neighbor_count"]
    if (
        pool_design == "controlled_dose"
        and isinstance(neighbor_type, str)
        and isinstance(neighbor_count, int)
        and not isinstance(neighbor_count, bool)
    ):
        if neighbor_type == "none" and neighbor_count != 0:
            errors.append(f"{prefix}: none neighbors require count=0")
        if neighbor_type in {"lexical", "functional_overlap"} and neighbor_count not in {
            4,
            8,
        }:
            errors.append(
                f"{prefix}: controlled lexical/functional count must be 4 or 8"
            )
        if neighbor_type == "mixed":
            errors.append(f"{prefix}: controlled_dose cannot use mixed neighbors")
    if (
        pool_design == "mixed_realistic"
        and isinstance(neighbor_type, str)
        and neighbor_type != "mixed"
    ):
        errors.append(
            f"{prefix}: mixed_realistic requires near_neighbor_type=mixed"
        )

    return errors


def validate_document(document: Any) -> list[str]:
    """Return every contract error without stopping at the first failure."""

    if not isinstance(document, dict):
        return ["document: must be an object"]

    errors: list[str] = []
    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version: must equal {SCHEMA_VERSION}")

    metadata = document.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("metadata: must be an object")
    else:
        for field in ("dataset_version", "protocol_version", "generated_at"):
            if not _non_empty_string(metadata.get(field)):
                errors.append(f"metadata.{field}: must be a non-empty string")
        if metadata.get("protocol_version") != PROTOCOL_VERSION:
            errors.append(f"metadata.protocol_version: must equal {PROTOCOL_VERSION}")

    records = document.get("records")
    if not isinstance(records, list) or not records:
        errors.append("records: must be a non-empty array")
        return errors

    seen: set[tuple[Any, ...]] = set()
    for index, record in enumerate(records):
        errors.extend(_validate_record(record, index))
        if not isinstance(record, dict) or not REQUIRED_RECORD_FIELDS <= record.keys():
            continue
        unique_values = (
            record["task_id"],
            record["tool_pool_id"],
            record["method"],
            record["model_run_repeat"],
        )
        if not (
            all(isinstance(value, str) for value in unique_values[:3])
            and isinstance(unique_values[3], int)
            and not isinstance(unique_values[3], bool)
        ):
            continue
        unique_key = unique_values
        if unique_key in seen:
            errors.append(
                f"records[{index}]: duplicate task/tool-pool/method/run cell {unique_key}"
            )
        seen.add(unique_key)

    return errors


def require_valid_document(document: Any) -> list[dict[str, Any]]:
    errors = validate_document(document)
    if errors:
        raise AnalysisValidationError(errors)
    return document["records"]


def selection_correct(record: dict[str, Any]) -> int | None:
    """Derive selection correctness without treating infrastructure absence as a model error."""

    if record["request_status"] == "not_accepted":
        return None
    if record["execution_status"] in {"provider_failure", "timeout"}:
        return None
    if record["execution_status"] in {"model_failure", "invalid_response"}:
        return 0
    return int(record["selected_tool"] in set(record["acceptable_tools"]))


def bootstrap_cluster_id(record: dict[str, Any]) -> str:
    return record["minimal_pair_group"] or f"TASK::{record['task_id']}"
