# Revenue Manager Agent

An AI Revenue Manager agent for a hotel General Manager, built for the
[otel-ai build challenge](https://github.com/otel-ai/otel-build-challenge).

It scrapes the live reservation data site into Postgres with an idempotent ETL,
puts a deliberate tool layer in front of it (semantic views and five named tools,
no raw SQL), and answers GM questions through a LangChain Deep Agent that uses
skills, a segment subagent, planning, memory, and a human-in-the-loop approval step.

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
| `PROJECT.clan` | Living project tracker (phases, decisions, status) |

## Quick start

```bash
docker compose up        # Postgres on :5432 (hotel_hackathon / hackathon / hackathon)
```

## Deploy (Neon Postgres + Render)

Live at **<https://otel-rm-agent.onrender.com>** (basic auth). It runs as two free pieces:
a **Neon** Postgres (persistent, no card) and the app on **Render** (free Docker web service
via `render.yaml`). Neither depends on a laptop being up.

**1. Load Neon.** Create a Neon project and copy the **pooled** connection string
(`...-pooler...neon.tech/<db>?sslmode=require`). Then load it once:

```bash
DATABASE_URL='postgresql://USER:PW@ep-xxx-pooler.<region>.aws.neon.tech/neondb?sslmode=require' \
  ./scripts/init_db.sh         # applies schema + cached scrape + views, prints row_hash
```

If your network blocks outbound `:5432` (so `init_db.sh` can't reach Neon), paste
[`neon_bootstrap.sql`](neon_bootstrap.sql) into Neon's **SQL Editor** instead; it does the
same thing over 443. Either way the printed `row_hash` must equal `etl/LOAD_PROOF.json`.

**2. Deploy on Render.** Dashboard → **New → Blueprint** → pick this repo (branch `main`)
→ Apply. `render.yaml` is detected; fill the secret env vars:

| Var | Value |
|-----|-------|
| `DATABASE_URL` | the same Neon string from step 1 |
| `MODEL` | `anthropic:claude-haiku-4-5` (primary) |
| `MODEL_FALLBACKS` | `cerebras:gpt-oss-120b,openrouter:openai/gpt-oss-120b:free` (tried in order if the primary errors before producing output) |
| `BASIC_AUTH_USER` / `BASIC_AUTH_PASS` | `gm` / your password |
| model-provider keys | `ANTHROPIC_API_KEY` (primary) plus `CEREBRAS_API_KEY` / `OPENROUTER_API_KEY` for the fallbacks |

The Dockerfile binds uvicorn to `$PORT`. Note: deploying from a public-repo URL keeps
**auto-deploy off**, so new commits need a service **Manual Deploy → Deploy latest commit**;
the free instance also spins down when idle (~50 s cold start).

**Keep-warm (avoid cold starts).** `.github/workflows/keep-warm.yml` self-loops, pinging
`/health` every 3 min to hold the free instance (and Neon) awake — resilient to GitHub's
frequently-delayed scheduled crons. For maximum reliability, also point an external monitor
([cron-job.org](https://cron-job.org) or [UptimeRobot](https://uptimerobot.com)) at
`https://otel-rm-agent.onrender.com/health` every 5 min (expect HTTP 200). The guaranteed
fix is upgrading the Render instance to **Starter** (always-on, no spin-down).

**3. Verify.**

```bash
curl -s https://otel-rm-agent.onrender.com/health   # row_hash must equal etl/LOAD_PROOF.json
```

See the [challenge brief](https://github.com/otel-ai/otel-build-challenge) for the
full domain reference and `PROJECT.clan` for build status (`clan read agent PROJECT.clan`).
