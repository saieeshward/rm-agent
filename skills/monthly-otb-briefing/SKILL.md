---
name: monthly-otb-briefing
description: "Use when the GM asks what revenue/room nights are on the books for a month, how a month is shaping up, or for an OTB summary. Frames get_otb_summary as a morning briefing with the right comparisons."
---

# Monthly OTB briefing

Call `get_otb_summary(stay_month)` for the on-the-books picture: `row_count`
(stay rows), `reservation_count` (distinct bookings), `room_nights`
(sum of rooms across nights), `room_revenue`, and `total_revenue`. This is the
default GM briefing universe: Posted, non-cancelled.

## How to brief, not just dump

- Never quote a number alone. Anchor every month to **same time last year** — run
  `get_otb_summary` on the prior-year month — and to the adjacent months, so the
  GM hears "ahead/behind" not just a figure.
- Lead with the headline (room nights and total revenue on the books, vs STLY),
  then the one driver worth knowing (hand off to `segment-mix-shift` or
  `pickup-pace` for the "why").
- Use `total_revenue` for the overall picture and `room_revenue` when the question
  is specifically about rooms; note that `total_revenue >= room_revenue` because
  total includes packages.

## Thresholds and actions

- **Total revenue behind STLY by > 10%** with arrival still > 60 days out — pace
  gap, not a loss; **hold BAR**, protect availability, and lean on `pickup-pace`
  to convert the open window.
- **Ahead of STLY by > 10%** — pricing power; **shift rate** up on the strong
  dates and tighten discount availability rather than adding more low-rate rooms.

Quote `reservation_count` for "how many bookings", `room_nights` for occupancy/
revenue questions — never `row_count`, which is stay rows, not bookings.
