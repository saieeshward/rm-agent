# Deploy — Revenue Manager Agent (Phase 6)

Goal: hosted Postgres + the FastAPI agent, with `GET /health`, a streaming chat
UI behind basic auth, kept up **≥ 7 days**.

Why not Vercel/serverless: the agent holds conversation memory and the
human-in-the-loop approve/reject state **in-process** (`MemorySaver`), and streams
over SSE. Serverless functions are stateless and time-limited, so `/resume` could
hit a different instance with no memory of the interrupt. This needs a **persistent
container + a managed Postgres**. Fly.io is the reference target below; Render and
Railway notes follow.

The image carries **no Playwright/Chromium** — the hosted DB is loaded once from the
cached scrape (`etl/.cache/raw.json`) via `scripts/init_db.sh`, so the container is
small and never scrapes.

Artifacts: `Dockerfile`, `requirements-deploy.txt`, `.dockerignore`, `fly.toml`,
`scripts/init_db.sh`.

---

## A. Fly.io (reference)

### 0. Install + login
```bash
brew install flyctl          # or: curl -L https://fly.io/install.sh | sh
fly auth login
```

### 1. Create the app (don't deploy yet)
```bash
fly launch --no-deploy --copy-config --name otel-rm-agent --region lhr
# if "otel-rm-agent" is taken, pick another name and update app = "..." in fly.toml
```

### 2. Provision + attach managed Postgres
```bash
fly postgres create --name otel-rm-db --region lhr   # pick the smallest dev plan
fly postgres attach otel-rm-db -a otel-rm-agent      # injects DATABASE_URL secret
```

### 3. Set secrets (model + auth)
```bash
fly secrets set -a otel-rm-agent \
  MODEL='openrouter:openai/gpt-4o-mini' \
  OPENROUTER_API_KEY='<your key>' \
  BASIC_AUTH_USER='gm' \
  BASIC_AUTH_PASS='<pick a strong password>'
# To upgrade the model later: fly secrets set MODEL=... (+ its API key). No code change.
```

### 4. Load the hosted DB (schema → cached data → views)
```bash
fly proxy 5432 -a otel-rm-db &                       # tunnel managed PG to localhost:5432
# grab the password from: fly postgres connect -a otel-rm-db   (or the attach output)
DATABASE_URL='postgresql://postgres:<pw>@localhost:5432/postgres' ./scripts/init_db.sh
kill %1                                               # stop the proxy
```
`init_db.sh` prints the loaded `row_hash` — confirm it equals the value in
`etl/LOAD_PROOF.json` and the data-site `/verify` page.

### 5. Deploy + verify
```bash
fly deploy -a otel-rm-agent
curl https://otel-rm-agent.fly.dev/health           # fingerprint == LOAD_PROOF / /verify
open  https://otel-rm-agent.fly.dev/                 # basic-auth chat UI (gm / your pass)
```

`fly.toml` sets `auto_stop_machines = false` + `min_machines_running = 1`, so the
machine stays up for the whole 7-day window. Watch it with `fly status` / `fly logs`.

---

## B. Render (alternative, no CLI)

1. Push the repo to GitHub.
2. New → **Postgres** (free) → copy the *External Database URL*.
3. Locally: `DATABASE_URL='<external url>' ./scripts/init_db.sh`
4. New → **Web Service** → from the repo, Docker runtime (uses `Dockerfile`).
5. Env vars: `DATABASE_URL` (the *internal* URL), `MODEL`, `OPENROUTER_API_KEY`,
   `BASIC_AUTH_USER`, `BASIC_AUTH_PASS`. Health check path: `/health`.
6. Note: the **free** web service spins down after ~15 min idle (slow cold start +
   loses in-memory conversation state). For a clean 7-day demo use the cheapest
   always-on instance.

## C. Railway (alternative)

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
