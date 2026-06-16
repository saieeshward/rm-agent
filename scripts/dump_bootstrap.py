"""
One-off: dump the locally-loaded hotel DB into a single self-contained SQL file
(scripts/../neon_bootstrap.sql) that can be pasted into Neon's SQL Editor (port
443) when this machine's network blocks the Postgres wire port (5432).

  schema.sql  +  INSERTs (Postgres-quoted via quote_nullable)  +  sql/views.sql

Identity columns (load_id, reservation_stay_id) are skipped so they regenerate;
the /health fingerprint is reservation_id|stay_date|financial_status, so the
row_hash is unaffected by surrogate ids.
"""
from __future__ import annotations

from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
SRC = "postgresql://hackathon:hackathon@localhost:5432/hotel_hackathon"

# FK-safe load order: parents before children.
TABLES = [
    "room_type_lookup",
    "rate_plan_lookup",
    "market_code_lookup",
    "channel_code_lookup",
    "market_macro_group_history",
    "load_manifest",
    "reservations_hackathon",
]

out = [
    "-- Neon bootstrap for the Revenue Manager Agent.",
    "-- Paste into the Neon SQL Editor and Run. Idempotent: re-running truncates + reloads.",
    "-- 1) schema  2) data (truncate-and-reload)  3) views.",
    "",
    "-- ============================== 1. SCHEMA ==============================",
    (ROOT / "schema.sql").read_text().strip(),
    "",
    "-- ============================== 2. DATA ===============================",
    "-- Option D (see etl/load.py): the live data uses more granular selling codes",
    "-- than the 8-row rate_plan_lookup, so this one FK is intentionally relaxed.",
    "alter table public.reservations_hackathon",
    "  drop constraint if exists reservations_hackathon_rate_plan_code_fkey;",
    "",
    "truncate table public.reservations_hackathon, public.market_macro_group_history,",
    "  public.load_manifest, public.room_type_lookup, public.rate_plan_lookup,",
    "  public.market_code_lookup, public.channel_code_lookup restart identity cascade;",
    "",
]

with psycopg.connect(SRC, connect_timeout=5) as conn, conn.cursor() as cur:
    for t in TABLES:
        cur.execute(
            "select column_name from information_schema.columns "
            "where table_schema='public' and table_name=%s and is_identity='NO' "
            "order by ordinal_position",
            (t,),
        )
        cols = [r[0] for r in cur.fetchall()]
        collist = ", ".join(cols)
        # Let Postgres quote each value as a text literal; the target column types
        # coerce it back (e.g. '123.45'->numeric, 'true'->boolean, dates/timestamps ok).
        tuple_expr = "'(' || concat_ws(',', " + ", ".join(f"quote_nullable({c}::text)" for c in cols) + ") || ')'"
        cur.execute(f"select {tuple_expr} from public.{t}")
        rows = [r[0] for r in cur.fetchall()]
        out.append(f"-- {t}: {len(rows)} rows")
        if rows:
            out.append(f"insert into public.{t} ({collist}) values")
            out.append(",\n".join(rows) + ";")
        out.append("")

out += [
    "-- ============================== 3. VIEWS ==============================",
    (ROOT / "sql" / "views.sql").read_text().strip(),
    "",
    "-- ============================== 4. VERIFY =============================",
    "select count(*) as reservation_rows from public.reservations_hackathon;",
    "select dataset_revision, row_hash from public.load_manifest order by load_id desc limit 1;",
    "",
]

(ROOT / "neon_bootstrap.sql").write_text("\n".join(out))
print(f"wrote neon_bootstrap.sql ({(ROOT / 'neon_bootstrap.sql').stat().st_size} bytes)")
