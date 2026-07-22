"""Unit tests for trace-store selection and fallback behavior."""

import os
import unittest
from unittest.mock import patch

from models_core.db import postgres_connect_kwargs
from models_core.trace_store import (
    InMemoryTraceStore,
    ResilientTraceStore,
    create_trace_store,
)


class AlwaysFailStore:
    backend_name = "failing"

    def save_execution(self, record):
        raise RuntimeError("database unavailable")

    def get_execution(self, execution_id):
        raise RuntimeError("database unavailable")

    def save_experiment(self, record):
        raise RuntimeError("database unavailable")

    def get_experiment(self, experiment_id):
        raise RuntimeError("database unavailable")

    def health(self):
        raise RuntimeError("database unavailable")


class TraceStoreTests(unittest.TestCase):
    def test_resilient_store_keeps_records_when_postgres_is_down(self):
        store = ResilientTraceStore(AlwaysFailStore(), InMemoryTraceStore())
        execution = {"execution_id": "EXEC-1", "value": 42}
        experiment = {"experiment_id": "EXP-1", "value": 84}

        store.save_execution(execution)
        store.save_experiment(experiment)

        self.assertEqual(store.get_execution("EXEC-1"), execution)
        self.assertEqual(store.get_experiment("EXP-1"), experiment)
        health = store.health()
        self.assertTrue(health["available"])
        self.assertFalse(health["persistent"])
        self.assertIn("database unavailable", health["last_error"])

    def test_memory_mode_is_explicitly_selectable(self):
        with patch.dict(os.environ, {"MODEL_TRACE_STORE": "memory"}):
            self.assertIsInstance(create_trace_store(), InMemoryTraceStore)

    def test_database_host_is_only_added_when_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            config = postgres_connect_kwargs()
        self.assertNotIn("host", config)
        self.assertEqual(config["dbname"], "metallurgy")
        self.assertEqual(config["user"], "postgres")


if __name__ == "__main__":
    unittest.main()
