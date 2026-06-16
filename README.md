# Revenue Manager Agent

An AI **Revenue Manager agent** for a hotel General Manager, built for the
[otel-ai build challenge](https://github.com/otel-ai/otel-build-challenge).

It scrapes the live reservation data site into Postgres via an idempotent ETL,
exposes a deliberate tool layer (semantic views + five named tools — no raw SQL),
and answers GM questions through a LangChain **Deep Agent** with skills,
a segment subagent, planning, memory, and human-in-the-loop approval.

## Layout

| Path | Purpose |
|------|---------|
| `schema.sql` | Postgres table definitions (load target) |
| `docker-compose.yml` | Local Postgres for development |
| `sql/` | Semantic views (`vw_stay_night_base`, `vw_segment_stay_night`, …) |
| `etl/` | Playwright scraper → transform → idempotent load; `SCRAPE_MANIFEST.json`, `LOAD_PROOF.json` |
| `tools/` | Five required tools + `METRIC_DEFINITIONS.md` |
| `skills/` | Deep Agents `SKILL.md` files (≥6, ≥3 judgment) |
| `agent/` | `create_deep_agent()` wiring + server (`/health`, streaming UI, basic auth) |
| `tests/` | `test_etl.py`, `test_tools.py`, `test_skills.py`, `test_agent.py` |
| `scripts/compute_load_fingerprint.py` | Generates `etl/LOAD_PROOF.json` |
| `docs/brief/` | Original challenge brief, tool contract, and submission docs (reference) |
| `PROJECT.clan` | Living project tracker (phases, decisions, status) |

## Quick start

```bash
docker compose up        # Postgres on :5432 (hotel_hackathon / hackathon / hackathon)
```

## Deploy (Neon Postgres + Render)

The hosted demo runs as two free pieces: a **Neon** Postgres (persistent, no card)
and the agent web app on **Render** (free Docker web service, see `render.yaml`).

```bash
# 1. Create a Neon project, copy its pooled connection string, then load it once:
DATABASE_URL='postgresql://USER:PW@ep-xxx.neon.tech/dbname?sslmode=require' \
  ./scripts/init_db.sh         # applies schema + cached data + views, prints row_hash

# 2. Render dashboard -> New -> Blueprint -> pick the repo -> Apply.
#    Fill the secret env vars (MODEL, OPENROUTER_API_KEY, DATABASE_URL=<same Neon URL>,
#    BASIC_AUTH_USER, BASIC_AUTH_PASS). The Dockerfile binds uvicorn to $PORT.

# 3. Confirm the deployed DB matches the proof (no auth needed on /health):
curl -s https://<your-app>.onrender.com/health   # row_hash must equal etl/LOAD_PROOF.json
```

See `docs/brief/CHALLENGE_BRIEF.md` for the full domain reference and `PROJECT.clan`
for current build status (`clan read agent PROJECT.clan`).
