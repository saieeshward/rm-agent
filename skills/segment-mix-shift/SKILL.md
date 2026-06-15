---
name: segment-mix-shift
description: "Use when the GM asks what is driving a month, how the segment/market mix is changing, corporate vs leisure vs MICE balance, or which segments to grow or protect. Judges segment share shifts and recommends a rebalancing action."
---

# Segment mix and what's driving the month

Call `get_segment_mix(stay_month)` for the breakdown by market with effective
`macro_group`, `share_of_revenue`, and `share_of_room_nights`. The job is to
explain *what is driving the month* and whether the mix is healthy, not just list
shares. The view already applies the **effective** macro group (e.g. PROM is
Leisure Group, not Retail, after its reclassification), so trust it over the
static lookup.

## How to judge

- "What's driving July?" = the top two or three segments by `share_of_revenue`,
  with the STLY comparison: run `get_segment_mix` on the prior-year month and call
  out which segments grew or shrank.
- Watch the spread between `share_of_revenue` and `share_of_room_nights` per
  segment: revenue share well above room-night share means that segment is
  high-rated (protect it); the reverse means it is diluting ADR.
- Use `macro_group="Retail"`, `"Corporate"`, etc. to size a macro group cleanly.

## Thresholds and actions

- **Retail (BAR/OTA/PROM) share_of_revenue < 25%** — over-reliant on
  group/contract demand; protect retail availability and **hold BAR** rather than
  releasing rooms to blocks.
- **One macro group > 50% of revenue** — diversification risk; grow the
  under-weight segments and avoid discounting the dominant one further.
- **A high-ADR segment's revenue share drops > 10 points vs STLY** — rate or mix
  erosion; **shift rate** and tighten discount availability for that segment.
