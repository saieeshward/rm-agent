  [x] 1. Scrape the live data site (Playwright, 100/page, list → detail) and load it into Postgres via an idempotent ETL. Match your load to /verify on scrape day.
  [x] 2. Build 2 SQL views + 5 exact tools (get_otb_summary, get_segment_mix, get_pickup_delta, get_as_of_otb, get_block_vs_transient_mix) that read views only — no raw-SQL tool. Bake grain/cancellation/date/revenue rules into the code.
  [x] 3. Write ≥6 skills (≥3 with a numeric threshold + recommended action) that teach revenue-manager judgment, not just metric definitions.
  [x] 4. Wire a LangChain Deep Agent using all building blocks: tools, skills, a subagent (segment work), planning, memory, and HITL approval on get_as_of_otb.
  [x] 5. Write tests: ETL ≥3, tools ≥10, skills ≥5, agent ≥4.
  6. Deploy hosted Postgres + agent + a UI that streams tool/skill calls + GET /health + basic auth, and keep it up ≥7 days.
  7. Commit the artifacts: ATTESTATION.md, etl/SCRAPE_MANIFEST.json, etl/LOAD_PROOF.json, tools/METRIC_DEFINITIONS.md, ARCHITECTURE.md, then submit repo + live
  URL + credentials.

  Watch the traps: grain (row ≠ reservation ≠ room night), two revenue columns, right date field, exclude cancelled+provisional by default, effective
  macro_group, and the otel_challenge_token honeypot (not in the schema — don't load it).

  Want me to start with the browser recon of the live site?