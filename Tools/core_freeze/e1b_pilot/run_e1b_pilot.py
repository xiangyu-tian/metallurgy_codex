"""Run and score E1b No-Tool versus Forced-Verified-Tool task pairs."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parents[1]
PROJECT_ROOT = HERE.parents[2]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from models_core import ModelRegistry  # noqa: E402
from models_core.llm_adapters import (  # noqa: E402
    DeepSeekOpenAIAdapter,
    LLMAdapterError,
)

from e1b_scoring import parse_and_score  # noqa: E402


SYSTEM_PROMPT = """你正在参加一个机器可评分的科学计算实验。
只返回一个符合给定答案Schema的JSON对象，不要使用Markdown代码块，不要添加解释。
所有数值必须是JSON number，不能写入单位字符串。"""


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_id() -> str:
    return f"E1B-RUN-{uuid.uuid4().hex[:16].upper()}"


def _tool_payload(result) -> dict[str, Any]:
    return {
        "success": result.success,
        "result": result.result,
        "error": result.error,
        "error_code": result.error_code,
        "boundary_check": {
            "passed": result.boundary_check.passed,
            "warnings": [
                {
                    "field": warning.field,
                    "message": warning.message,
                    "level": warning.level,
                }
                for warning in result.boundary_check.warnings
            ],
        },
        "runtime_ms": result.runtime_ms,
    }


def build_messages(
    task: dict[str, Any],
    condition: str,
    tool_result: dict[str, Any] | None,
) -> list[dict[str, str]]:
    schema_text = json.dumps(
        task["answer_schema"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    system = f"{SYSTEM_PROMPT}\n答案Schema：{schema_text}"
    if condition == "no_tool":
        system += "\n本条件禁止使用任何外部工具；请直接作答。"
        user = task["problem_text"]
    elif condition == "forced_verified_oracle_parameters":
        system += (
            "\n本条件已使用预注册参数执行验证工具。"
            "请忠实依据工具结果填写最终JSON，不得改写核心数值。"
        )
        user = (
            f"{task['problem_text']}\n"
            "验证工具结果："
            f"{json.dumps(tool_result, ensure_ascii=False, sort_keys=True)}"
        )
    else:
        raise ValueError(f"unsupported E1b condition: {condition}")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def run_cell(
    *,
    task: dict[str, Any],
    condition: str,
    repeat: int,
    registry: ModelRegistry,
    adapter,
    run_config: dict[str, Any],
) -> dict[str, Any]:
    executed_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    tool_execution = None
    response = None
    raw_answer = ""
    status = "completed"
    error_type = None
    error_message = None

    try:
        if condition == "forced_verified_oracle_parameters":
            tool_result = registry.invoke(
                task["source_tool_id"],
                task["expected_parameters"],
            )
            tool_execution = _tool_payload(tool_result)
            if not tool_result.success:
                status = "tool_error"
                error_type = tool_result.error_code or "TOOL_ERROR"
                error_message = tool_result.error or "verified tool execution failed"
                raise RuntimeError(error_message)
        messages = build_messages(task, condition, tool_execution)
        response = adapter.complete(
            messages,
            temperature=float(run_config["temperature"]),
            max_tokens=int(run_config["max_tokens"]),
        )
        raw_answer = response["message"].get("content") or ""
    except LLMAdapterError as exc:
        status = "provider_error"
        error_type = type(exc).__name__
        error_message = str(exc)
    except RuntimeError:
        pass
    except Exception as exc:  # keep one failed cell auditable without losing the run
        status = "internal_error"
        error_type = type(exc).__name__
        error_message = str(exc)

    scoring = parse_and_score(raw_answer, task["scoring_rule"])
    return {
        "cell_id": f"{task['task_id']}::{condition}::R{repeat}",
        "executed_at": executed_at,
        "task_id": task["task_id"],
        "task_family_id": task["task_family_id"],
        "task_pair_id": task["task_pair_id"],
        "condition": condition,
        "model_run_repeat": repeat,
        "provider": run_config["provider"],
        "model": run_config["model"],
        "prompt_version": run_config["prompt_version"],
        "source_tool_id": task["source_tool_id"],
        "source_tool_version": task["source_tool_version"],
        "contract_id": task["contract_id"],
        "contract_hash": task["contract_hash"],
        "status": status,
        "error_type": error_type,
        "error_message": error_message,
        "tool_execution": tool_execution,
        "raw_answer": raw_answer,
        "response_metadata": {
            "id": response.get("id") if response else None,
            "model": response.get("model") if response else None,
            "finish_reason": response.get("finish_reason") if response else None,
            "usage": response.get("usage") if response else None,
        },
        **scoring,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    condition_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pair_rows: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in records:
        condition_rows[record["condition"]].append(record)
        pair_rows[
            (record["task_id"], record["model_run_repeat"])
        ][record["condition"]] = record

    by_condition = {}
    for condition, rows in sorted(condition_rows.items()):
        completed = [row for row in rows if row["status"] == "completed"]
        by_condition[condition] = {
            "cell_count": len(rows),
            "completed_count": len(completed),
            "correct_count": sum(row["correct"] for row in completed),
            "accuracy": (
                sum(row["correct"] for row in completed) / len(completed)
                if completed
                else None
            ),
            "parse_failure_count": sum(
                row["parse_status"] != "parsed" for row in rows
            ),
            "status_counts": dict(
                sorted(Counter(row["status"] for row in rows).items())
            ),
        }

    paired_differences = []
    for pair in pair_rows.values():
        forced = pair.get("forced_verified_oracle_parameters")
        no_tool = pair.get("no_tool")
        if (
            forced
            and no_tool
            and forced["status"] == "completed"
            and no_tool["status"] == "completed"
        ):
            paired_differences.append(
                int(forced["correct"]) - int(no_tool["correct"])
            )
    accuracy_gain = (
        sum(paired_differences) / len(paired_differences)
        if paired_differences
        else None
    )
    return {
        "cell_count": len(records),
        "by_condition": by_condition,
        "scheduled_pair_count": len(pair_rows),
        "paired_complete_count": len(paired_differences),
        "incomplete_pair_count": len(pair_rows) - len(paired_differences),
        "descriptive_accuracy_gain": accuracy_gain,
        "status": (
            "completed"
            if records and all(row["status"] == "completed" for row in records)
            else "completed_with_failures"
        ),
        "confirmatory_inference_allowed": False,
    }


def run_experiment(
    *,
    tasks_doc: dict[str, Any],
    run_config: dict[str, Any],
    registry: ModelRegistry,
    adapter,
    repeats: int,
    max_tasks: int | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    tasks = tasks_doc["tasks"]
    if max_tasks is not None:
        if max_tasks < 1:
            raise ValueError("max_tasks must be at least 1")
        tasks = tasks[:max_tasks]

    records = []
    for repeat in range(1, repeats + 1):
        for task in tasks:
            for condition in run_config["primary_conditions"]:
                records.append(
                    run_cell(
                        task=task,
                        condition=condition,
                        repeat=repeat,
                        registry=registry,
                        adapter=adapter,
                        run_config=run_config,
                    )
                )
    return records, summarize(records)


def write_outputs(
    *,
    output_dir: Path,
    tasks_path: Path,
    config_path: Path,
    tasks_doc: dict[str, Any],
    run_config: dict[str, Any],
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    adapter_configuration: dict[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    run_id = _run_id()
    tasks_snapshot_path = output_dir / "task_source_snapshot.json"
    config_snapshot_path = output_dir / "run_config_snapshot.json"
    runner_snapshot_path = output_dir / "runner_source_snapshot.py"
    scorer_snapshot_path = output_dir / "scoring_source_snapshot.py"
    shutil.copyfile(tasks_path, tasks_snapshot_path)
    shutil.copyfile(config_path, config_snapshot_path)
    shutil.copyfile(Path(__file__), runner_snapshot_path)
    shutil.copyfile(HERE / "e1b_scoring.py", scorer_snapshot_path)
    records_path = output_dir / "run_records.jsonl"
    with records_path.open("x", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(
                json.dumps(
                    {"run_id": run_id, **record},
                    ensure_ascii=False,
                )
                + "\n"
            )

    report_path = output_dir / "run_report.json"
    report = {
        "schema_version": "1.0",
        "run_id": run_id,
        "dataset_id": tasks_doc["dataset_id"],
        "run_config_id": run_config["run_config_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "task_source_sha256": file_hash(tasks_path),
        "run_config_sha256": file_hash(config_path),
        "source_snapshots": {
            "tasks": tasks_snapshot_path.name,
            "run_config": config_snapshot_path.name,
            "runner": runner_snapshot_path.name,
            "scoring": scorer_snapshot_path.name,
        },
        "adapter_configuration": adapter_configuration,
        "summary": summary,
        "formal_repeats_frozen": False,
        "core_frozen": False,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest_path = output_dir / "artifact_manifest.json"
    manifest = {
        "schema_version": "1.0",
        "run_id": run_id,
        "artifacts": [
            {"filename": records_path.name, "sha256": file_hash(records_path)},
            {"filename": report_path.name, "sha256": file_hash(report_path)},
            {
                "filename": tasks_snapshot_path.name,
                "sha256": file_hash(tasks_snapshot_path),
            },
            {
                "filename": config_snapshot_path.name,
                "sha256": file_hash(config_snapshot_path),
            },
            {
                "filename": runner_snapshot_path.name,
                "sha256": file_hash(runner_snapshot_path),
            },
            {
                "filename": scorer_snapshot_path.name,
                "sha256": file_hash(scorer_snapshot_path),
            },
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tasks",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "e1b_pilot_v1_20260730" / "e1b_tasks.json",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=HERE / "run_config_v1.json",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repeats", type=int)
    parser.add_argument("--max-tasks", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tasks_doc = load_json(args.tasks)
    run_config = load_json(args.config)
    adapter = DeepSeekOpenAIAdapter.from_environment()
    adapter.timeout = float(run_config["timeout_seconds"])
    if adapter.model != run_config["model"]:
        raise RuntimeError(
            f"configured model mismatch: environment={adapter.model}, "
            f"run_config={run_config['model']}"
        )
    if adapter.base_url != run_config["openai_base_url"]:
        raise RuntimeError(
            f"base URL mismatch: environment={adapter.base_url}, "
            f"run_config={run_config['openai_base_url']}"
        )
    if adapter.thinking != run_config["thinking"]:
        raise RuntimeError(
            f"thinking mismatch: environment={adapter.thinking}, "
            f"run_config={run_config['thinking']}"
        )
    adapter.ensure_ready()

    registry = ModelRegistry()
    registry.discover()
    repeats = (
        args.repeats
        if args.repeats is not None
        else int(run_config["development_repeats"])
    )
    records, summary = run_experiment(
        tasks_doc=tasks_doc,
        run_config=run_config,
        registry=registry,
        adapter=adapter,
        repeats=repeats,
        max_tasks=args.max_tasks,
    )
    report = write_outputs(
        output_dir=args.output_dir,
        tasks_path=args.tasks,
        config_path=args.config,
        tasks_doc=tasks_doc,
        run_config=run_config,
        records=records,
        summary=summary,
        adapter_configuration=adapter.configuration(),
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
