# Deploy — Revenue Manager Agent (Phase 6)

Goal: hosted Postgres + the FastAPI agent, with `GET /health`, a streaming chat
UI behind basic auth, kept up **≥ 7 days**.

> **CURRENT LIVE DEPLOYMENT: Neon (Postgres) + Render (app).**
> Live URL: <https://otel-rm-agent.onrender.com>. The README "Deploy (Neon +
> Render)" section + `render.yaml` are the canonical steps; the Neon DB is loaded
> from `neon_bootstrap.sql` (or `scripts/init_db.sh`). Section A below mirrors that.

Why not Vercel/serverless: the agent holds conversation memory and the
human-in-the-loop approve/reject state **in-process** (`MemorySaver`), and streams
over SSE. Serverless functions are stateless and time-limited, so `/resume` could
hit a different instance with no memory of the interrupt. This needs a **persistent
container + a managed Postgres** — Render (app) + Neon (Postgres) below; Railway is
an alternative.

The image carries **no Playwright/Chromium** — the hosted DB is loaded once from the
cached scrape (`etl/.cache/raw.json`) via `scripts/init_db.sh`, so the container is
small and never scrapes.

Artifacts: `Dockerfile`, `requirements-deploy.txt`, `.dockerignore`, `render.yaml`,
`scripts/init_db.sh`, `neon_bootstrap.sql`.

---

## A. Render + Neon (live target)

This is what's deployed. The Postgres lives on **Neon** (free, persistent), the app
on **Render** (free Docker web service via `render.yaml`).

1. **Neon:** create a project, copy the **pooled** connection string (`...-pooler...
   ?sslmode=require`). Load it once — paste `neon_bootstrap.sql` into the Neon **SQL
   Editor** (works over 443 when local `:5432` egress is firewalled), or run
   `DATABASE_URL='<neon url>' ./scripts/init_db.sh`. Confirm the printed `row_hash`
   equals `etl/LOAD_PROOF.json` and the data-site `/verify`.
2. **Render:** New → **Blueprint** → pick the repo → `render.yaml` is detected.
3. Fill the secret env vars: `DATABASE_URL` (the Neon string), `MODEL`
   (`google_genai:gemini-2.5-flash`), `BASIC_AUTH_USER`, `BASIC_AUTH_PASS`, and any
   model-provider keys you want live (`GOOGLE_API_KEY`, `CEREBRAS_API_KEY`,
   `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`). `healthCheckPath: /health`.
4. Verify: `curl https://<app>.onrender.com/health` → `row_hash` matches the proof.
5. Note: the **free** web service spins down after ~15 min idle (~50s cold start;
   in-memory conversation state resets). Render-from-public-URL has auto-deploy off,
   so new commits need a service **Manual Deploy → Deploy latest commit**.

## B. Railway (alternative)

1. New project → **Deploy from repo** (uses `Dockerfile`) → add the **Postgres** plugin.
2. App reads `DATABASE_URL` from the plugin reference; add `MODEL`,
   `OPENROUTER_API_KEY`, `BASIC_AUTH_USER`, `BASIC_AUTH_PASS`.
3. Locally load the DB: `DATABASE_URL='<public PG url>' ./scripts/init_db.sh`.

---

## Refreshing the data during the live window

The data site regenerates daily. To re-anchor the hosted DB to a new day:
```bash
. .venv/bin/activate && python -m etl.run_etl        # fresh scrape into the cache
python scripts/compute_load_fingerprint.py --manifest etl/SCRAPE_MANIFEST.json \
  --output etl/LOAD_PROOF.json                        # refresh the proof
# then re-point DATABASE_URL at the hosted DB and re-run:
DATABASE_URL='<hosted>' ./scripts/init_db.sh          # idempotent truncate-and-reload
```
`/health` will reflect the new `row_hash` immediately (computed live from the DB).

## Submission checklist (Phase 7)

- [ ] Live URL reachable; `/health` fingerprint matches `etl/LOAD_PROOF.json` + `/verify`
- [ ] Basic-auth credentials shared with the reviewer
- [ ] Repo pushed (code + `ATTESTATION.md`, `etl/SCRAPE_MANIFEST.json`,
      `etl/LOAD_PROOF.json`, `tools/METRIC_DEFINITIONS.md`, `ARCHITECTURE.md`)
- [ ] Deployment kept up ≥ 7 days
