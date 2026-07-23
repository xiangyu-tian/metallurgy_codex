"""Trace-store contract and persistence implementations."""

from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, Protocol

from .db import connect_postgres


class TraceStore(Protocol):
    def save_execution(self, record: dict) -> None: ...
    def get_execution(self, execution_id: str) -> Optional[dict]: ...
    def save_experiment(self, record: dict) -> None: ...
    def get_experiment(self, experiment_id: str) -> Optional[dict]: ...
    def health(self) -> dict: ...


def _as_datetime(value):
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromtimestamp(float(value), tz=timezone.utc)


def _as_timestamp(value):
    if isinstance(value, datetime):
        return value.timestamp()
    return value


def _error_text(value) -> Optional[str]:
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


class InMemoryTraceStore:
    """Thread-safe fallback used by tests and when PostgreSQL is unavailable."""

    backend_name = "memory"

    def __init__(self):
        self._executions: Dict[str, dict] = {}
        self._experiments: Dict[str, dict] = {}
        self._lock = threading.RLock()

    def save_execution(self, record: dict) -> None:
        with self._lock:
            self._executions[record["execution_id"]] = deepcopy(record)

    def get_execution(self, execution_id: str) -> Optional[dict]:
        with self._lock:
            record = self._executions.get(execution_id)
            return deepcopy(record) if record else None

    def save_experiment(self, record: dict) -> None:
        with self._lock:
            self._experiments[record["experiment_id"]] = deepcopy(record)

    def get_experiment(self, experiment_id: str) -> Optional[dict]:
        with self._lock:
            record = self._experiments.get(experiment_id)
            return deepcopy(record) if record else None

    def health(self) -> dict:
        return {"backend": self.backend_name, "persistent": False, "available": True}


class PostgresTraceStore:
    """PostgreSQL implementation matching migration 003."""

    backend_name = "postgres"

    def __init__(self, connection_factory: Optional[Callable[[], object]] = None):
        self._connection_factory = connection_factory or connect_postgres

    def _connect(self):
        return self._connection_factory()

    def save_execution(self, record: dict) -> None:
        from psycopg2.extras import Json

        conn = self._connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO metallurgy_v2.model_execution_log (
                            execution_id, trace_id, model_code, model_version,
                            input_json, actual_data_records, boundary_check,
                            output_json, status, error_code, error_message,
                            runtime_ms, user_or_agent, started_at, completed_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (execution_id) DO UPDATE SET
                            output_json = EXCLUDED.output_json,
                            status = EXCLUDED.status,
                            error_code = EXCLUDED.error_code,
                            error_message = EXCLUDED.error_message,
                            runtime_ms = EXCLUDED.runtime_ms,
                            completed_at = EXCLUDED.completed_at
                        """,
                        (
                            record["execution_id"], record["trace_id"],
                            record["model_code"], record.get("model_version"),
                            Json(record.get("input", {})),
                            Json(record.get("actual_data_records", [])),
                            Json(record.get("boundary_check")),
                            Json(record.get("output")), record["status"],
                            record.get("error_code"), _error_text(record.get("error")),
                            record.get("runtime_ms"), record.get("user_or_agent", "api"),
                            _as_datetime(record.get("started_at")),
                            _as_datetime(record.get("completed_at")),
                        ),
                    )
        finally:
            conn.close()

    def get_execution(self, execution_id: str) -> Optional[dict]:
        from psycopg2.extras import RealDictCursor

        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT execution_id, trace_id, model_code, model_version,
                           input_json, actual_data_records, boundary_check,
                           output_json, status, error_code, error_message,
                           runtime_ms, user_or_agent, started_at, completed_at
                    FROM metallurgy_v2.model_execution_log
                    WHERE execution_id = %s
                    """,
                    (execution_id,),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return {
            "execution_id": row["execution_id"],
            "trace_id": row["trace_id"],
            "model_code": row["model_code"],
            "model_version": row["model_version"],
            "input": row["input_json"],
            "actual_data_records": row["actual_data_records"],
            "boundary_check": row["boundary_check"],
            "output": row["output_json"],
            "status": row["status"],
            "error_code": row["error_code"],
            "error": row["error_message"],
            "runtime_ms": float(row["runtime_ms"] or 0),
            "user_or_agent": row["user_or_agent"],
            "started_at": _as_timestamp(row["started_at"]),
            "completed_at": _as_timestamp(row["completed_at"]),
        }

    def save_experiment(self, record: dict) -> None:
        from psycopg2.extras import Json

        conn = self._connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO metallurgy_v2.llm_tool_trace (
                            trace_id, user_query, llm_name, prompt_version, mode,
                            experiment_engine,
                            candidate_models, selected_model, selection_reason,
                            generated_arguments, validation_result, execution_result,
                            tool_call_chain, llm_trace, retry_count, final_answer,
                            latency_ms, token_usage, created_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (trace_id) DO UPDATE SET
                            experiment_engine = EXCLUDED.experiment_engine,
                            candidate_models = EXCLUDED.candidate_models,
                            selected_model = EXCLUDED.selected_model,
                            selection_reason = EXCLUDED.selection_reason,
                            generated_arguments = EXCLUDED.generated_arguments,
                            validation_result = EXCLUDED.validation_result,
                            execution_result = EXCLUDED.execution_result,
                            tool_call_chain = EXCLUDED.tool_call_chain,
                            llm_trace = EXCLUDED.llm_trace,
                            retry_count = EXCLUDED.retry_count,
                            final_answer = EXCLUDED.final_answer,
                            latency_ms = EXCLUDED.latency_ms,
                            token_usage = EXCLUDED.token_usage
                        """,
                        (
                            record["trace_id"], record["user_query"],
                            record.get("llm_name", "external-orchestrator"),
                            record.get("prompt_version", "v1"), record["mode"],
                            record.get("engine", "deterministic"),
                            Json(record.get("candidate_models", [])),
                            record.get("selected_model"), record.get("selection_reason"),
                            Json(record.get("generated_arguments", {})),
                            Json(record.get("validation_result")),
                            Json(record.get("execution_result")),
                            Json(record.get("tool_call_chain", [])),
                            Json(record.get("llm_trace", {})),
                            record.get("retry_count", 0), record.get("final_answer"),
                            record.get("latency_ms"), Json(record.get("token_usage")),
                            _as_datetime(record.get("created_at")),
                        ),
                    )
                    cur.execute(
                        """
                        INSERT INTO metallurgy_v2.experiment_run (
                            experiment_id, trace_id, benchmark_case_id,
                            benchmark_run_id, mode,
                            result_validation_enabled, status, metrics_json, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (experiment_id) DO UPDATE SET
                            benchmark_run_id = EXCLUDED.benchmark_run_id,
                            status = EXCLUDED.status,
                            metrics_json = EXCLUDED.metrics_json
                        """,
                        (
                            record["experiment_id"], record["trace_id"],
                            record.get("benchmark_case_id"),
                            record.get("benchmark_run_id"), record["mode"],
                            record.get("result_validation_enabled", True),
                            record.get("status", "completed"),
                            Json(record.get("metrics", {})),
                            _as_datetime(record.get("created_at")),
                        ),
                    )
        finally:
            conn.close()

    def get_experiment(self, experiment_id: str) -> Optional[dict]:
        from psycopg2.extras import RealDictCursor

        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT er.experiment_id, er.benchmark_case_id, er.benchmark_run_id,
                           er.result_validation_enabled, er.status,
                           er.metrics_json, trace.*
                    FROM metallurgy_v2.experiment_run er
                    JOIN metallurgy_v2.llm_tool_trace trace
                      ON trace.trace_id = er.trace_id
                    WHERE er.experiment_id = %s
                    """,
                    (experiment_id,),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            return None
        llm_trace = row["llm_trace"] or {}
        return {
            "experiment_id": row["experiment_id"],
            "trace_id": row["trace_id"],
            "benchmark_case_id": row["benchmark_case_id"],
            "benchmark_run_id": row["benchmark_run_id"],
            "user_query": row["user_query"],
            "mode": row["mode"],
            "engine": row["experiment_engine"],
            "llm_name": row["llm_name"],
            "prompt_version": row["prompt_version"],
            "candidate_models": row["candidate_models"],
            "selected_model": row["selected_model"],
            "selection_reason": row["selection_reason"],
            "generated_arguments": row["generated_arguments"],
            "validation_result": row["validation_result"],
            "execution_result": row["execution_result"],
            "tool_call_chain": row["tool_call_chain"],
            "llm_trace": llm_trace,
            "tool_round_count": llm_trace.get("tool_round_count", 0),
            "retry_count": row["retry_count"],
            "stop_reason": llm_trace.get("stop_reason"),
            "result_validation_enabled": row["result_validation_enabled"],
            "final_answer": row["final_answer"],
            "latency_ms": float(row["latency_ms"] or 0),
            "token_usage": row["token_usage"],
            "status": row["status"],
            "metrics": row["metrics_json"],
            "created_at": _as_timestamp(row["created_at"]),
        }

    def health(self) -> dict:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            return {"backend": self.backend_name, "persistent": True, "available": True}
        finally:
            conn.close()


class ResilientTraceStore:
    """Persist to PostgreSQL while retaining an in-process availability fallback."""

    backend_name = "postgres+memory"

    def __init__(self, primary: TraceStore, fallback: Optional[TraceStore] = None):
        self.primary = primary
        self.fallback = fallback or InMemoryTraceStore()
        self.last_error: Optional[str] = None

    def _save(self, method: str, record: dict) -> None:
        getattr(self.fallback, method)(record)
        try:
            getattr(self.primary, method)(record)
            self.last_error = None
        except Exception as exc:
            self.last_error = str(exc)

    def _get(self, method: str, identifier: str) -> Optional[dict]:
        try:
            record = getattr(self.primary, method)(identifier)
            self.last_error = None
            if record is not None:
                return record
        except Exception as exc:
            self.last_error = str(exc)
        return getattr(self.fallback, method)(identifier)

    def save_execution(self, record: dict) -> None:
        self._save("save_execution", record)

    def get_execution(self, execution_id: str) -> Optional[dict]:
        return self._get("get_execution", execution_id)

    def save_experiment(self, record: dict) -> None:
        self._save("save_experiment", record)

    def get_experiment(self, experiment_id: str) -> Optional[dict]:
        return self._get("get_experiment", experiment_id)

    def health(self) -> dict:
        try:
            primary_health = self.primary.health()
            self.last_error = None
        except Exception as exc:
            self.last_error = str(exc)
            primary_health = {
                "backend": getattr(self.primary, "backend_name", "primary"),
                "persistent": True,
                "available": False,
            }
        return {
            "backend": self.backend_name,
            "persistent": primary_health["available"],
            "available": True,
            "primary": primary_health,
            "fallback": self.fallback.health(),
            "last_error": self.last_error,
        }


def create_trace_store() -> TraceStore:
    mode = os.getenv("MODEL_TRACE_STORE", "auto").strip().lower()
    if mode == "memory":
        return InMemoryTraceStore()
    if mode == "postgres":
        return PostgresTraceStore()
    if mode == "auto":
        return ResilientTraceStore(PostgresTraceStore())
    raise ValueError("MODEL_TRACE_STORE must be one of: auto, postgres, memory")
