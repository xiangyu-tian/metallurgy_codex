"""Opt-in integration test for migration 003 and PostgreSQL trace storage."""

import os
import time
import unittest
import uuid

from models_core.db import connect_postgres
from models_core.trace_store import PostgresTraceStore


@unittest.skipUnless(
    os.getenv("RUN_POSTGRES_TESTS") == "1",
    "set RUN_POSTGRES_TESTS=1 to exercise the local PostgreSQL database",
)
class PostgresTraceStoreIntegrationTests(unittest.TestCase):
    def setUp(self):
        suffix = uuid.uuid4().hex[:12].upper()
        self.execution_id = f"EXEC-TEST-{suffix}"
        self.trace_id = f"TRACE-TEST-{suffix}"
        self.experiment_id = f"EXP-TEST-{suffix}"
        self.store = PostgresTraceStore()

    def tearDown(self):
        conn = connect_postgres()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM metallurgy_v2.experiment_run WHERE experiment_id = %s",
                        (self.experiment_id,),
                    )
                    cur.execute(
                        "DELETE FROM metallurgy_v2.llm_tool_trace WHERE trace_id = %s",
                        (self.trace_id,),
                    )
                    cur.execute(
                        "DELETE FROM metallurgy_v2.model_execution_log WHERE execution_id = %s",
                        (self.execution_id,),
                    )
        finally:
            conn.close()

    def test_execution_and_experiment_round_trip(self):
        now = time.time()
        execution = {
            "execution_id": self.execution_id,
            "trace_id": self.trace_id,
            "model_code": "A003",
            "model_version": "1.0.0",
            "input": {"formula": "Fe2O3"},
            "actual_data_records": [],
            "boundary_check": {"passed": True, "warnings": []},
            "output": {"molar_mass": 159.687},
            "status": "success",
            "error": None,
            "error_code": None,
            "runtime_ms": 1.25,
            "started_at": now,
            "completed_at": now + 0.01,
            "user_or_agent": "integration-test",
        }
        self.store.save_execution(execution)
        loaded_execution = self.store.get_execution(self.execution_id)
        self.assertEqual(loaded_execution["output"], execution["output"])
        self.assertEqual(loaded_execution["model_code"], "A003")

        experiment = {
            "experiment_id": self.experiment_id,
            "trace_id": self.trace_id,
            "user_query": "计算 Fe2O3 的摩尔质量",
            "mode": "forced",
            "llm_name": "integration-test",
            "prompt_version": "v1",
            "candidate_models": [{"model_code": "A003", "score": 1}],
            "selected_model": "A003",
            "selection_reason": "integration test",
            "generated_arguments": {"formula": "Fe2O3"},
            "validation_result": {"valid": True, "errors": []},
            "execution_result": execution,
            "retry_count": 0,
            "result_validation_enabled": True,
            "final_answer": "159.687 g/mol",
            "latency_ms": 2.5,
            "token_usage": None,
            "created_at": now,
        }
        self.store.save_experiment(experiment)
        loaded_experiment = self.store.get_experiment(self.experiment_id)
        self.assertEqual(loaded_experiment["selected_model"], "A003")
        self.assertEqual(loaded_experiment["execution_result"]["output"], execution["output"])
