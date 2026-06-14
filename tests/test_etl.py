"""
Phase 1 ETL property tests (tests/ETL_TEST_SCENARIOS.md).

Assume a correct scrape -> load (run `python -m etl.run_etl --use-cache`, then
`scripts/compute_load_fingerprint.py`). These assert structural properties of
the loaded DB and reconcile it with the committed proofs. Live /verify
reconciliation happens at ETL time (the site regenerates daily); CI reconciles
DB <-> SCRAPE_MANIFEST.json <-> LOAD_PROOF.json, which are stable for an anchor.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read_json(rel: str):
    return json.loads((ROOT / rel).read_text())


# --- Scenario 1: lookup row counts ---
def test_lookup_row_counts(loaded):
    expected = {
        "room_type_lookup": 3,
        "rate_plan_lookup": 8,
        "market_code_lookup": 10,
        "market_macro_group_history": 11,
        "channel_code_lookup": 4,
    }
    with loaded.cursor() as cur:
        for table, n in expected.items():
            cur.execute(f"select count(*) from public.{table}")
            assert cur.fetchone()[0] == n, f"{table} expected {n}"


# --- Scenario 2: fact-table grain uniqueness ---
def test_fact_grain_unique(loaded):
    with loaded.cursor() as cur:
        cur.execute(
            "select count(*), count(distinct (reservation_id, stay_date)) "
            "from public.reservations_hackathon"
        )
        total, distinct_pairs = cur.fetchone()
    assert total == distinct_pairs, "duplicate (reservation_id, stay_date) pairs present"


# --- Scenario 3: manifest <-> DB reconciliation ---
def test_manifest_reconciles_db(loaded):
    manifest = _read_json("etl/SCRAPE_MANIFEST.json")
    with loaded.cursor() as cur:
        cur.execute("select count(distinct reservation_id) from public.reservations_hackathon")
        db_count = cur.fetchone()[0]
        cur.execute("select distinct reservation_id from public.reservations_hackathon order by 1")
        ids = [r[0] for r in cur.fetchall()]
    db_sha = hashlib.sha256("\n".join(ids).encode()).hexdigest()
    assert manifest["reservation_ids_count"] == db_count
    assert manifest["reservation_ids_sha256"] == db_sha


def test_dataset_revision_matches_manifest(loaded):
    manifest = _read_json("etl/SCRAPE_MANIFEST.json")
    with loaded.cursor() as cur:
        cur.execute("select dataset_revision from public.load_manifest order by load_id desc limit 1")
        db_rev = cur.fetchone()[0]
    assert db_rev == manifest["dataset_revision"]


def test_load_proof_sha_matches_db(loaded):
    proof = _read_json("etl/LOAD_PROOF.json")
    with loaded.cursor() as cur:
        cur.execute(
            "select reservation_id, stay_date::text, financial_status "
            "from public.reservations_hackathon "
            "order by reservation_id, stay_date, financial_status"
        )
        lines = [f"{a}|{b}|{c}" for a, b, c in cur.fetchall()]
    db_sha = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    assert proof["reservation_stay_status_sha256"] == db_sha


# --- Scenario 4 (bonus): stay-row expansion equals nights ---
def test_stay_row_expansion_equals_nights(loaded):
    with loaded.cursor() as cur:
        cur.execute(
            "select reservation_id, max(nights) as nights, count(*) as stay_rows "
            "from public.reservations_hackathon "
            "group by reservation_id having max(nights) > 1"
        )
        multi = cur.fetchall()
    assert multi, "expected at least one multi-night reservation"
    mismatches = [(rid, n, rows) for rid, n, rows in multi if rows != n]
    assert not mismatches, f"stay rows != nights for: {mismatches[:5]}"
