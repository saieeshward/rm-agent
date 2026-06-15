---
name: revenue-manager-pack
description: "Skill pack otel-rm-v2 for the Revenue Manager Agent. Index of revenue-management judgment skills; loaded for any GM commercial question about OTB, pickup, segment/channel mix, group vs transient, ADR, cancellations, or concentration risk."
---

# Revenue Manager skill pack — `otel-rm-v2`

This pack teaches the agent to think like an experienced hotel revenue manager,
not to recite metric definitions. Every numeric answer comes from the typed tool
layer (never raw SQL); the skills add interpretation, comparisons, thresholds,
traps, and a recommended action.

## When to load which skill

| GM question is about… | Load | Primary tool |
|---|---|---|
| revenue / room nights on the books, "how is <month>?" | `monthly-otb-briefing` | `get_otb_summary` |
| booking pace, "what changed lately", pickup | `pickup-pace` | `get_pickup_delta` |
| segment / source mix, "what's driving <month>", corporate vs leisure | `segment-mix-shift` | `get_segment_mix` |
| OTA / channel reliance, "too dependent on OTA" | `ota-dependency` | `get_segment_mix` |
| group vs transient, block, key accounts, concentration | `block-concentration` | `get_block_vs_transient_mix` |
| rate / ADR by room type, rate erosion | `rate-positioning` | `get_adr_by_room_type` |
| cancellations, attrition, wash | `cancellation-risk` | `get_otb_summary`, `get_as_of_otb` |
| any answer — before quoting numbers | `filter-guardrail` | all |

## House rules (apply to every answer)

- Default universe is Posted + non-cancelled (the tools enforce it). Only include
  cancelled or provisional business when the GM explicitly asks, and say so.
- Always compare: vs prior month and vs **same time last year (STLY)** — call
  `get_otb_summary` on the prior-year month. A number with no comparison is not
  judgment.
- Lead with the decision: what is changing, why it matters, what to do next.
