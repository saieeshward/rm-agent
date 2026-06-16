"""
Postgres access for the tool layer — a lazily-opened connection POOL.

A pool (not a single shared connection) because the deployed agent server is
concurrent: multiple chat turns / tool calls can hit the DB at once. Importing
the tools does not open the pool (so modules import with no DB / no server); the
pool opens on first query and hands out short-lived read-only connections.

Tools pass typed parameters only — never SQL strings from the model — so every
query here is parameterised.
"""

from __future__ import annotations

import os
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DEFAULT_DATABASE_URL = "postgresql://hackathon:hackathon@localhost:5432/hotel_hackathon"

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
            min_size=1,
            max_size=int(os.environ.get("DB_POOL_MAX", "10")),
            kwargs={"autocommit": True},
            # Hosted Postgres (e.g. Neon serverless) drops idle connections, so a pooled
            # connection can be dead by the time it is handed out. check
            # validates (and replaces) a connection before each use; max_idle /
            # max_lifetime recycle them so we never sit on a server-closed socket.
            check=ConnectionPool.check_connection,
            max_idle=60.0,
            max_lifetime=600.0,
            open=True,
        )
    return _pool


def query(sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    """Run a parameterised SELECT and return rows as dicts."""
    with get_pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()


def query_one(sql: str, params: tuple | list | None = None) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
