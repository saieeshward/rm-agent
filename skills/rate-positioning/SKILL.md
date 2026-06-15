---
name: rate-positioning
description: "Use when the GM asks about ADR, rate, which room type earns most, rate erosion, or the premium between room classes. NOT for segment/channel mix — use segment-mix-shift. Calls get_adr_by_room_type and get_otb_summary."
---

# Rate positioning / ADR by room type

**Do (exact).** `get_adr_by_room_type(month)` → `adr_room_avg` (booked rate) and
`revenue_per_room_night` (realised rate) per room type, ranked. Compare each to
STLY (same month, year−1). When ADR looks soft, confirm it's rate not demand with
`get_otb_summary` (room nights at/ahead of STLY = rate problem, not volume).

**Decide:**

| signal | read | action |
|---|---|---|
| room-type ADR down > 10% vs STLY, pace healthy | rate erosion | **hold BAR**, pull discount codes, **shift rate** up on strong dates |
| Executive-to-Standard premium < £40 | ladder compressed | reprice the premium room up, protect it from discounting |
| `revenue_per_room_night` < 90% of `adr_room_avg` | package/comp leakage | review which rate plans erode realised rate |

Judgment: the premium room class should sit clearly above standard; thin spread
means the top product is underpriced, not that demand is weak.

**Answer like.** "Executive King runs £245 ADR vs King £190 and Twin £177 — a
healthy £55 premium, and all three are flat-to-up vs STLY. No erosion; if
anything I'd test a small Executive increase on the high-demand weekends."

**Don't** read ADR off raw rows — `revenue_per_room_night` already weights by
room nights.
