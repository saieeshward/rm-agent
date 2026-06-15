---
name: rate-positioning
description: "Use when the GM asks about ADR, rate, which room type earns most, rate erosion, or the premium between room classes. Judges ADR by room type and recommends a rate move."
---

# Rate positioning / ADR by room type

Call `get_adr_by_room_type(stay_month)` for `adr_room_avg` (reservation-level rate)
and `revenue_per_room_night` (realised rate per occupied room-night) by room type,
joined to display names. ADR is the price lever; the judgment is whether rate is
holding, eroding, or compressed across the room ladder.

## How to judge

- Rank room types by `adr_room_avg`; the Executive/premium type should sit clearly
  above Standard. Check the **premium spread** between the top and entry room
  class — if it is thin, the rate ladder is compressed and the premium product is
  underpriced.
- Compare each room type's ADR to the **same month last year** (`get_adr_by_room_type`
  on the prior-year month) and to neighbouring months for trend.
- Read `revenue_per_room_night` vs `adr_room_avg`: realised well below the booked
  rate signals discounting, comps, or package dilution.

## Thresholds and actions

- **ADR down > 10% vs STLY** for a room type with healthy pace — rate erosion, not
  a demand problem. Confirm the month's demand is sound with `get_otb_summary`
  (room nights at/ahead of STLY); if so, **hold BAR**, pull back discount codes,
  and **shift rate** up on the strong dates.
- **Executive-to-Standard premium < £40** — ladder compressed; reprice the premium
  room type upward and protect it from discounting.
- **revenue_per_room_night < 90% of adr_room_avg** — leakage from packages/comps;
  review which rate plans are eroding realised rate.
