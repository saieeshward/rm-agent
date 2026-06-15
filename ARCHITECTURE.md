# ARCHITECTURE

Revenue Manager Agent for a hotel GM. ETL → Postgres → semantic views → typed tool
layer → LangChain Deep Agent (skills, subagent, planning, memory, HITL) → web app.

## 1. ETL boundary
- **Extract** (`etl/scrape.py`): Playwright (headless Chromium, assets blocked) pages
  the client-rendered list (100/page) and drills into each `/reservations/<id>` detail
  (`<dl>` fields + per-night stay-rows table), concurrently. Raw snapshot → `etl/.cache/`.
- **Transform** (`etl/transform.py`): expands to the **reservation × stay_date** grain,
  types every field, drops non-schema fields (e.g. `commercial_rate_code`, and any
  honeypot — there is **no** `otel_challenge_token`).
- **Load** (`etl/load.py`): idempotent single-transaction truncate-and-reload (lookups →
  facts), `load_manifest` row per run, `row_hash = reservation_stay_status_sha256`.
- **Verify**: `SCRAPE_MANIFEST.json` + `LOAD_PROOF.json` reconcile with `/verify`; the
  load sha matches the site (`da950a13…`). Anchor date 2026-06-14 — **re-scrape same-day
  before submit**.

## 2. Database and views
- Local Postgres via `docker compose`; hosted Postgres (Neon/Supabase) for deploy.
- Tools read **only** semantic views (`sql/views.sql`), never `reservations_hackathon`:
  - `vw_stay_night_base` — Posted + non-cancelled (default OTB)
  - `vw_segment_stay_night` — base + market_name + **effective** macro_group (history-dated)
  - `vw_stay_night_posted` — Posted incl. cancelled (for `exclude_cancelled=False` / as-of)
- **Option D (documented deviation):** the live data uses 16 commercial rate codes vs the
  8-row `rate_plan_lookup`; per the changelog the commercial code *is* `rate_plan_code`, so
  we load it verbatim, keep the lookup at 8, and relax that one FK at load. No tool reads
  `rate_plan_code`, so no metric is affected.

## 3. Tool layer
Five required tools (exact names) + two supplementary, all views-only, no raw-SQL param,
grain in every docstring (see `tools/METRIC_DEFINITIONS.md`):
`get_otb_summary`, `get_segment_mix`, `get_pickup_delta`, `get_as_of_otb`,
`get_block_vs_transient_mix` (+ `get_adr_by_room_type`, `get_booking_pace`). Cancellation &
provisional defaults are baked into the views; arbitrary SQL is never exposed (the model
picks a tool + typed args; correctness lives in our tested code).

## 4. Deep Agents wiring (`agent/build.py`)
| Block | Use |
|---|---|
| Tools | main: OTB/pickup/ADR/booking-pace/as-of; subagent: segment-mix/block — main lacks mix tools so segment Qs **must** delegate |
| Skills | `skills=` → `skills/` (progressive disclosure) via a `FilesystemBackend` |
| Subagent | `segment-analyst` (task tool) for segment/channel/group/concentration |
| Planning | built-in `write_todos` |
| Memory | `MemorySaver` checkpointer (multi-turn) + `InMemoryStore` |
| HITL | `interrupt_on={"get_as_of_otb": True}` (expensive point-in-time rebuild) |
| Model | env `MODEL` (`resolve_model`): anthropic / google_genai / openrouter / ollama — provider-agnostic |

## 5. Skill → tool routing matrix
| Skill | Primary tool(s) | Judgment? |
|---|---|---|
| monthly-otb-briefing | get_otb_summary | Y |
| pickup-pace | get_pickup_delta, get_booking_pace | Y |
| segment-mix-shift | get_segment_mix | Y |
| ota-dependency | get_segment_mix | Y |
| block-concentration | get_block_vs_transient_mix | Y |
| rate-positioning | get_adr_by_room_type, get_otb_summary | Y |
| cancellation-risk | get_otb_summary, get_as_of_otb | Y |
| filter-guardrail | all (adversarial guardrail) | N |

(8 skills, 7 judgment; `CHALLENGE_SKILL.md` pins `otel-rm-v2` + answer contract.)

## 6. Tests (`tests/`, run with no live LLM)
- `test_etl.py` (6), `test_tools.py` (12), `test_skills.py` (7), `test_agent.py` (7) — 32 total.
- Agent tests build the graph with a fake chat model and assert: 5 required tools + no
  `run_sql`; `interrupt_on` includes `get_as_of_otb`; segment isolated to the subagent;
  skills + checkpointer configured; multi-tool decomposition (trace fixture).
- `evals/` gold set + `check_facts.py` verify answer numbers against the live tools (6/6).

## 7. Deployment topology (`agent/server.py`)
- FastAPI: `/` chat UI (streams tool **and** skill calls live), `/chat` + `/resume` (SSE;
  HITL approve/reject), all behind **HTTP basic auth** (`BASIC_AUTH_USER/PASS`).
- `GET /health` (no auth, no model): computed from the live DB → `db_fingerprint`,
  `dataset_revision`, `row_hash`, `financial_status_posted_only_rows` — matches `LOAD_PROOF`.
- Model key via env/`.env` (gitignored) — **never committed**.

## 8. Out of scope / decisions
- Kept 6+ tools (5 required + 2 supplementary); "exactly five" read as floor + no raw-SQL.
- Model-agnostic; reliable subagent nesting needs a capable model (Claude / paid Gemini /
  OpenRouter credits) — free tiers loop or rate-limit.
