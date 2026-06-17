# ARCHITECTURE

A Revenue Manager agent for a hotel GM. The flow is ETL into Postgres, a couple of
semantic views on top, a small typed tool layer, then a LangChain Deep Agent (skills,
a subagent, planning, memory, HITL) served as a web app.

## 1. ETL boundary
- Extract (`etl/scrape.py`): Playwright (headless Chromium, assets blocked) pages the
  client-rendered list 100 at a time and opens each `/reservations/<id>` detail (the `<dl>`
  fields plus the per-night stay-rows table), run concurrently. The raw snapshot lands in
  `etl/.cache/`.
- Transform (`etl/transform.py`): expands to the reservation × stay_date grain, types every
  field, and drops anything not in the schema (e.g. `commercial_rate_code`, and the honeypot;
  there is no `otel_challenge_token`).
- Load (`etl/load.py`): one idempotent transaction that truncates and reloads (lookups, then
  facts) and writes a `load_manifest` row each run, with `row_hash = reservation_stay_status_sha256`.
- Verify: `SCRAPE_MANIFEST.json` and `LOAD_PROOF.json` reconcile with `/verify`, and the load
  sha matches the site (`3388ad54…`). Anchor date is 2026-06-16; I re-scrape the same day before
  submitting.

## 2. Database and views
- Local Postgres via `docker compose`; hosted on Neon for the live deploy.
- Tools read only the semantic views (`sql/views.sql`), never `reservations_hackathon`:
  - `vw_stay_night_base`: Posted and non-cancelled (the default OTB universe)
  - `vw_segment_stay_night`: base, plus market_name and the effective, history-dated macro_group
  - `vw_stay_night_posted`: Posted including cancelled (for `exclude_cancelled=False` and as-of)
- Option D (a documented deviation): the live data carries 16 commercial rate codes against an
  8-row `rate_plan_lookup`. The changelog says the commercial code *is* `rate_plan_code`, so I
  load it verbatim, keep the lookup at 8, and relax just that FK at load. No tool reads
  `rate_plan_code`, so no metric is affected.

## 3. Tool layer
Five required tools (exact names) plus two extras, all views-only, none taking a SQL string,
with the grain spelled out in every docstring (see `tools/METRIC_DEFINITIONS.md`):
`get_otb_summary`, `get_segment_mix`, `get_pickup_delta`, `get_as_of_otb`,
`get_block_vs_transient_mix`, and the supplementary `get_adr_by_room_type` and `get_booking_pace`.
Cancellation and provisional defaults live in the views. The model never sees raw SQL; it picks a
tool and typed args, and the correctness sits in tested code.

## 4. Deep Agents wiring (`agent/build.py`)
| Block | Use |
|---|---|
| Tools | main: OTB/pickup/ADR/booking-pace/as-of; subagent: segment-mix/block — main lacks mix tools so segment Qs **must** delegate |
| Skills | `skills=` → `skills/` (progressive disclosure) via a `FilesystemBackend` |
| Subagent | `segment-analyst` (task tool) for segment/channel/group/concentration |
| Planning | built-in `write_todos` |
| Memory | `MemorySaver` checkpointer (multi-turn) + `InMemoryStore` |
| HITL | `interrupt_on={"get_as_of_otb": True}` (expensive point-in-time rebuild) |
| Model | Claude Opus 4.8 (single model, no in-app picker); override at deploy via env `MODEL` (`resolve_model`): anthropic / openai / google_genai / openrouter / groq / cerebras / ollama |

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

8 skills, 7 with judgment; `CHALLENGE_SKILL.md` pins `otel-rm-v2` and the answer contract.

## 6. Tests (`tests/`, no live LLM)
- `test_etl.py` (6), `test_tools.py` (15), `test_skills.py` (7), `test_agent.py` (7), 35 in total.
- The agent tests build the graph with a fake chat model and check: the 5 required tools are
  present with no `run_sql`, `interrupt_on` covers `get_as_of_otb`, segment work is isolated to the
  subagent, skills and the checkpointer are wired, and a multi-tool plan runs (trace fixture).
- `evals/` has a gold set and `check_facts.py` checks answer numbers against the live tools (6/6).

## 7. Deployment (`agent/server.py`)
- Neon (Postgres) + Render (app) at <https://otel-rm-agent.onrender.com> (`render.yaml`; Neon
  loaded from `neon_bootstrap.sql`). The FastAPI `/` chat UI streams both tool and skill calls live
  with timing, `/chat` and `/resume` run over SSE with HITL approve/reject, and the whole thing sits
  behind HTTP basic auth.
- `GET /health` (no auth, no model) returns `db_fingerprint`, `dataset_revision`, `row_hash` and
  `financial_status_posted_only_rows` from the live DB, matching `LOAD_PROOF`.
- The desk runs a single model — Claude Opus 4.8 — chosen for reliable tool-calling. Change it at
  deploy time with the `MODEL` env var (`resolve_model` supports anthropic / openai / google_genai /
  openrouter / groq / cerebras / ollama). Keys come from env/`.env` and are never committed.

## 8. Decisions / out of scope
- I kept 7 tools (5 required + 2 extras); "exactly five" reads to me as a floor plus the no-raw-SQL rule.
- The agent is model-agnostic, but reliable subagent nesting wants a capable model (Claude, paid
  Gemini, OpenRouter credits); the weakest free tiers tend to loop or rate-limit.
