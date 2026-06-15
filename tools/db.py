"""
Thin Postgres access layer for the tool layer.

- Lazy connection: importing the tools does NOT open a connection (so modules
  import without a running DB / agent server). The connection opens on the first
  query and is reused; a dropped connection is transparently reopened once.
- Read-only autocommit. Tools pass typed parameters only — never SQL strings
  from the model — so all queries here are parameterised.
"""

from __future__ import annotations

import os
from typing import Any

import psycopg
from psycopg.rows import dict_row

DEFAULT_DATABASE_URL = "postgresql://hackathon:hackathon@localhost:5432/hotel_hackathon"

_conn: psycopg.Connection | None = None


def _connect() -> psycopg.Connection:
    return psycopg.connect(
        os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
        autocommit=True,
    )


def get_conn() -> psycopg.Connection:
    global _conn
    if _conn is None or _conn.closed:
        _conn = _connect()
    return _conn


def query(sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    """Run a parameterised SELECT and return rows as dicts."""
    try:
        conn = get_conn()
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    except psycopg.OperationalError:
        # connection went away — reopen once and retry
        global _conn
        _conn = _connect()
        with _conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()


def query_one(sql: str, params: tuple | list | None = None) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None
