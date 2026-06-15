---
name: ota-dependency
description: "Use when the GM asks whether the hotel is too dependent on OTA, about channel reliance, Booking.com/Expedia exposure, or direct-vs-OTA share. Judges OTA concentration of revenue and recommends an action."
---

# OTA dependency / channel concentration

Pull the segment mix with `get_segment_mix(stay_month)` and read OTA's
`share_of_revenue` (and `share_of_room_nights`). OTA is acquisition cost you pay
on every booking, so the judgment is about *how much margin you are renting*.

## Thresholds (share_of_revenue)

- **< 15%** — healthy/low. OTA is a useful flex channel; in soft months you can
  lean on it more, not less.
- **15–25%** — normal. Monitor; no action.
- **25–35%** — elevated. Defend direct: tighten OTA allocation in high-demand
  dates, enforce rate parity, and **hold BAR** so OTA never undercuts the website.
- **> 35%** — over-dependent. **Push direct** (member rates, retargeting), raise
  OTA-only rates, and **close OTA** or cap allocation on your peak/compression
  dates so commissionable rooms don't crowd out direct demand.

## How to judge, not just report

- Compare OTA's share to the **same month last year** via `get_segment_mix` on the
  prior-year month. A rising OTA share on flat total revenue means you are buying
  the same business at higher cost — flag it.
- Cross-check absolute demand: high OTA share in a *soft* month is acceptable
  (fill the hotel); high OTA share in a *strong* month is margin you are giving
  away — that is where you act.
- Tie the recommendation to dates: name the specific months where OTA
  `share_of_revenue` exceeds 35% and what to close or reprice there.

Never read OTA share from raw rows — always use `get_segment_mix` so cancelled
and provisional business is already excluded.
