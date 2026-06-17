---
name: revenue-manager-pack
description: "Skill pack otel-rm-v2 for the Revenue Manager Agent. Routing index + answer contract for GM commercial questions (OTB, pickup, segment/channel mix, group vs transient, ADR, cancellations, concentration). Load the matching skill below; never answer numbers from memory."
---

# Revenue Manager pack — `otel-rm-v2`

Numbers come from the typed tools; skills add the judgment. Pick one skill by the
table, follow its protocol, answer in the contract shape.

## Routing (load exactly one)

| GM asks about… | Load | Tool |
|---|---|---|
| revenue / room nights on the books, "how's <month>?" | `monthly-otb-briefing` | `get_otb_summary` |
| year-on-year, "vs last year", is it rate or volume | `monthly-otb-briefing` | `get_otb_comparison` |
| pace, pickup, "what changed lately" | `pickup-pace` | `get_pickup_delta` |
| what's driving a month, corporate/leisure/MICE mix | `segment-mix-shift` | `get_segment_mix` |
| OTA / channel reliance, "too dependent on OTA" | `ota-dependency` | `get_segment_mix` (market `OTA`) |
| group vs transient, blocks, key-account concentration | `block-concentration` | `get_block_vs_transient_mix` |
| ADR / rate by room type, rate erosion | `rate-positioning` | `get_adr_by_room_type` |
| cancellations, attrition, wash | `cancellation-risk` | `get_cancellation_summary`, `get_as_of_otb` |
| any answer (safety net) | `filter-guardrail` | all |

## Answer contract (every reply)

1. **Headline** — the decision/finding in one sentence.
2. **Numbers** — the figure, always vs **STLY** (same month, year−1) and/or prior month.
3. **Driver** — the one reason that matters.
4. **Recommendation** — a concrete action.
5. **Caveat** — only if a filter assumption was made (e.g. cancelled excluded).

**Sanity-check before answering.** Reconcile derived claims: block + transient
room nights must equal the month's OTB room nights; segment shares must sum to ~1;
a share must be 0–1. If a figure doesn't reconcile, re-pull rather than report it.

## House rules

- Default universe is Posted + non-cancelled (tools enforce it). Include cancelled
  or provisional only on explicit request, and say so.
- **STLY is mechanical:** the prior-year month is the same month with the year
  minus one (e.g. `2026-07` → `2025-07`). Call the same tool on it.
- Lead with the decision, not the dashboard.
