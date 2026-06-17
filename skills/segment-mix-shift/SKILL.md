---
name: segment-mix-shift
description: "Use when the GM asks what's driving a month, how the segment/market mix is changing, corporate vs leisure vs MICE balance, or which segments to grow or protect. NOT for OTA reliance (use ota-dependency) or group concentration (use block-concentration). Calls get_segment_mix."
---

# Segment mix / what's driving the month

**Do (exact).** `get_segment_mix(month)` → segments with effective `macro_group`,
`share_of_revenue`, `share_of_room_nights`. The view already applies the
stay-date-effective macro group (e.g. PROM is Leisure Group, not Retail, after its
2025-06-01 reclassification) — trust it. Pull STLY (same month, year−1) and call
out which segments grew or shrank. For "what share is corporate / MICE / retail?",
read the pre-computed `macro_rollup` (each macro group's share) — never sum segment
shares yourself; `macro_group="Retail"` also filters to one group cleanly.

**Decide:**

| signal | read | action |
|---|---|---|
| retail `share_of_revenue` < 25% (read the `Retail` row of `macro_rollup` — do not sum segments yourself; note BAR + OTA are Retail, and PROM is now Leisure Group) | over-reliant on group/contract | **protect retail** availability, **hold BAR** vs releasing to blocks |
| one macro group > 50% of revenue | diversification risk | grow under-weight segments; don't discount the dominant one |
| high-ADR segment's revenue share drops > 10 pts vs STLY | rate/mix erosion | **shift rate**, tighten that segment's discounts |

Judgment: revenue share well above room-night share = a high-rated segment to
protect; the reverse = a segment diluting ADR.

**Answer like.** "July is driven by MICE — CNI 42% and EVEN 22% of revenue —
while retail is only ~20%. Healthy demand but thin on rate-flexible business;
I'd protect retail availability and hold BAR on the shoulder dates."

**Answer like (act).** "Watch August: Corporate's revenue share fell ~12 points vs
STLY while OTA grew — a high-rated segment eroding. I'd shift rate back toward
corporate and tighten OTA discount availability there."

**Don't** use the static `market_code_lookup.macro_group` — the tool's effective
group is correct.
