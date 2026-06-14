# ARCHITECTURE.md (Phase 3 template)

Copy to your solution repo as `ARCHITECTURE.md` and replace placeholders.
Keep to **one page**.

---

## 1. ETL boundary

- **Extract:** how Playwright paginates the list (page size) and drills into detail pages
- **Transform:** grain enforcement (`reservation × stay_date`), typing, lookup loads
- **Load:** idempotency strategy (upsert / truncate-reload)
- **Verify:** how `LOAD_PROOF.json` and `/verify` are reconciled; anchor date recorded

## 2. Database and views

- Hosted Postgres provider
- Whether `sql/VIEWS.example.sql` (or equivalent) sits between tools and raw tables

## 3. Tool layer

- List all **five** required tools and which view(s) each uses
- How cancellation and provisional defaults are applied
- Why arbitrary SQL is **not** exposed to the model
- Link to `tools/METRIC_DEFINITIONS.md` for grain definitions

## 4. Deep Agents wiring (required)

| Building block | Your use (required unless noted) |
|----------------|----------------------------------|
| Tools | Five named tools — no `run_sql` |
| Skills | ≥6 `SKILL.md` files; progressive disclosure |
| Subagents | **Required:** segment/mix or pickup delegated via task tool |
| Planning | Multi-part GM questions decomposed before tool calls |
| Memory / filesystem | Multi-turn context — not stateless chat |
| Human-in-the-loop | **Required:** `get_as_of_otb` behind approval interrupt |
| Model & system prompt | Revenue-manager persona; answer style per brief §12 |

## 5. Skill → tool routing matrix

| Skill (name) | Primary tool(s) | Judgment? (Y/N) |
|--------------|-----------------|-----------------|
| | | |
| | | |
| | | |

- At least **3** skills encode judgment (threshold + recommended action)
- Document which skills load for OTB vs pickup vs mix vs block questions

## 6. Agent tests

- `tests/test_agent.py` — how HITL on `get_as_of_otb` and subagent routing are asserted
- `tests/test_skills.py` — how judgment thresholds are validated without LLM calls

## 7. Deployment topology

- DB, agent backend, UI (LangGraph / Agent Chat UI / custom)
- `GET /health` fields: `db_fingerprint`, `dataset_revision`, `row_hash`,
  `financial_status_posted_only_rows`
- Where API keys live (never in git)

## 8. Out of scope (optional)

- What you deliberately did **not** build and why
