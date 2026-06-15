---
name: monthly-otb-briefing
description: "Use when the GM asks what revenue/room nights are on the books for a month, how a month is shaping up, or for an OTB summary. NOT for pace/pickup (use pickup-pace) or segment drivers (use segment-mix-shift). Calls get_otb_summary."
---

# Monthly OTB briefing

**Do (exact).** `get_otb_summary(month)` → `reservation_count` (bookings),
`room_nights`, `room_revenue`, `total_revenue` (Posted, non-cancelled). Always
pull STLY (same month, year−1) the same way, and the adjacent month, so you can
say "ahead/behind", not just a figure. Hand the "why" to `segment-mix-shift` or
`pickup-pace`.

**Decide:**

| signal | read | action |
|---|---|---|
| total revenue behind STLY > 10%, arrival > 60 days out | pace gap, not a loss | **hold BAR**, protect availability, lean on pickup to convert |
| ahead of STLY > 10% | pricing power | **shift rate** up, tighten discounts vs adding low-rate rooms |

Judgment: a number with no comparison is not a briefing. Lead with room nights and
total revenue vs STLY, then the single driver worth knowing.

**Answer like.** "September is £42.9k on the books across 230 room nights — about
13% ahead of STLY and the strongest month in the window. It's group-led, so I'd
hold BAR and protect transient availability rather than discount."

**Don't** quote `row_count` as bookings — that's stay rows. Use `reservation_count`
for bookings, `room_nights` for occupancy/revenue.
