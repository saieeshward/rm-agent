"""Shared pytest fixtures. Tool/ETL tests run against the loaded Postgres."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = "postgresql://hackathon:hackathon@localhost:5432/hotel_hackathon"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


@pytest.fixture(scope="session")
def conn():
    try:
        c = psycopg.connect(database_url())
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Postgres not reachable ({exc}); run docker compose up + ETL first")
    yield c
    c.close()


@pytest.fixture(scope="session")
def loaded(conn):
    """Skip the whole suite if the fact table is empty (ETL not run yet)."""
    with conn.cursor() as cur:
        cur.execute("select count(*) from public.reservations_hackathon")
        if cur.fetchone()[0] == 0:
            pytest.skip("reservations_hackathon is empty; run `python -m etl.run_etl` first")
    return conn
