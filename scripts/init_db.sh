#!/usr/bin/env bash
# Initialise a hosted Postgres for the Revenue Manager Agent:
#   1. apply schema.sql        (tables + constraints)
#   2. load the cached scrape  (idempotent truncate-and-reload from etl/.cache/raw.json)
#   3. apply views.sql         (semantic views the tools read)
#   4. print the row_hash so you can confirm it matches etl/LOAD_PROOF.json / /verify
#
# Point DATABASE_URL at the TARGET database, then run from the repo root, e.g.:
#   Fly:    fly proxy 5432 -a otel-rm-db &           # tunnel the managed PG to localhost
#           DATABASE_URL='postgresql://postgres:<pw>@localhost:5432/postgres' ./scripts/init_db.sh
#   Render: DATABASE_URL='<external connection string>' ./scripts/init_db.sh
#
# Re-runnable: the load truncates and reloads, so running it again just refreshes the data.
set -euo pipefail

: "${DATABASE_URL:?set DATABASE_URL to the target hosted Postgres}"
cd "$(dirname "$0")/.."

PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"

echo "==> 1/3 applying schema.sql"
"$PY" - <<'PY'
import os, psycopg
sql = open("schema.sql").read()
with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
    c.execute(sql)
print("    schema applied")
PY

echo "==> 2/3 loading cached scrape (etl/.cache/raw.json)"
"$PY" -m etl.run_etl --use-cache

echo "==> 3/3 applying views.sql"
"$PY" - <<'PY'
import os, psycopg
sql = open("sql/views.sql").read()
with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
    c.execute(sql)
print("    views applied")
PY

echo "==> verifying row_hash in hosted DB"
"$PY" - <<'PY'
import os, psycopg
with psycopg.connect(os.environ["DATABASE_URL"]) as c, c.cursor() as cur:
    cur.execute("select count(*) from public.reservations_hackathon")
    n = cur.fetchone()[0]
    cur.execute("select dataset_revision, row_hash from public.load_manifest order by load_id desc limit 1")
    rev, h = cur.fetchone()
print(f"    fact rows={n}  dataset_revision={rev}")
print(f"    row_hash={h}")
print("    compare row_hash against etl/LOAD_PROOF.json and the data-site /verify page.")
PY
echo "done."
