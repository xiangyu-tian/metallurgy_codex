"""Seal an early E1b run by embedding immutable task and config snapshots."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from run_e1b_pilot import file_hash


def seal_run(output_dir: Path, tasks_path: Path, config_path: Path) -> dict:
    report_path = output_dir / "run_report.json"
    records_path = output_dir / "run_records.jsonl"
    manifest_path = output_dir / "artifact_manifest.json"
    for required in (report_path, records_path, manifest_path, tasks_path, config_path):
        if not required.is_file():
            raise FileNotFoundError(required)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    if file_hash(tasks_path) != report["task_source_sha256"]:
        raise ValueError("current task source does not match the recorded run hash")
    if file_hash(config_path) != report["run_config_sha256"]:
        raise ValueError("current run config does not match the recorded run hash")

    tasks_snapshot = output_dir / "task_source_snapshot.json"
    config_snapshot = output_dir / "run_config_snapshot.json"
    old_manifest_hash = file_hash(manifest_path)
    if tasks_snapshot.exists() or config_snapshot.exists():
        raise FileExistsError("run already contains source snapshots")
    shutil.copyfile(tasks_path, tasks_snapshot)
    shutil.copyfile(config_path, config_snapshot)

    report["source_snapshots"] = {
        "tasks": tasks_snapshot.name,
        "run_config": config_snapshot.name,
    }
    report["sealing"] = {
        "sealed_at": datetime.now(timezone.utc).isoformat(),
        "reason": "embed immutable sources before pilot task revision",
        "previous_manifest_sha256": old_manifest_hash,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "schema_version": "1.0",
        "run_id": report["run_id"],
        "artifacts": [
            {"filename": records_path.name, "sha256": file_hash(records_path)},
            {"filename": report_path.name, "sha256": file_hash(report_path)},
            {"filename": tasks_snapshot.name, "sha256": file_hash(tasks_snapshot)},
            {"filename": config_snapshot.name, "sha256": file_hash(config_snapshot)},
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    report = seal_run(args.output_dir, args.tasks, args.config)
    print(
        json.dumps(
            {
                "run_id": report["run_id"],
                "source_snapshots": report["source_snapshots"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
