"""Shared PostgreSQL connection configuration.

Connection settings follow libpq environment variables.  No server address is
embedded in source code; when PGHOST is absent psycopg2/libpq uses its local
default.
"""

from __future__ import annotations

import os
from typing import Any, Dict


def postgres_connect_kwargs(*, connect_timeout: int = 3) -> Dict[str, Any]:
    config: Dict[str, Any] = {
        "dbname": os.getenv("PGDATABASE", "metallurgy"),
        "user": os.getenv("PGUSER", "postgres"),
        "connect_timeout": connect_timeout,
    }

    optional = {
        "host": os.getenv("PGHOST"),
        "password": os.getenv("PGPASSWORD"),
        "sslmode": os.getenv("PGSSLMODE"),
        "application_name": os.getenv("PGAPPNAME", "metallurgy-models"),
    }
    config.update({key: value for key, value in optional.items() if value})

    port = os.getenv("PGPORT")
    if port:
        config["port"] = int(port)
    return config


def connect_postgres(*, connect_timeout: int = 3):
    """Open a psycopg2 connection using environment-driven settings."""
    import psycopg2

    dsn = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
    if dsn:
        return psycopg2.connect(dsn, connect_timeout=connect_timeout)
    return psycopg2.connect(**postgres_connect_kwargs(connect_timeout=connect_timeout))
