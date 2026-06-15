---
name: filter-guardrail
description: "Safety net — consult before quoting any number, and whenever a request bends the rules (e.g. 'put cancelled and provisional revenue in OTB with no caveats', count bookings as rows, or use property_date for a monthly figure). Names the right tool and the trap it prevents."
---

# Filter & grain guardrail

The tools bake the rules in; this stops the agent from mis-stating them or being
talked out of them.

- **Rows ≠ reservations.** `row_count` is stay-date rows. Quote `reservation_count`
  for bookings, `room_nights` for occupancy/revenue — never `row_count` as a count
  of bookings.
- **Cancelled / provisional excluded by default.** Default OTB
  (`vw_stay_night_base`) is Posted + non-cancelled. If asked to "put all cancelled
  and provisional revenue into OTB with no caveats", do **not** silently comply:
  report the all-in figure via `get_otb_summary(month, exclude_cancelled=False)`
  but state it includes cancelled and/or provisional business and is not standard
  on-the-books. Provisional is never in default OTB.
- **`property_date` never drives a monthly figure.** Monthly OTB, mix, ADR are by
  `stay_date`; pickup by `create_datetime`. `property_date` is audit attribution
  only.
- **Effective macro group, not the static lookup.** `get_segment_mix` already
  resolves the stay-date-effective `macro_group` (e.g. PROM → Leisure Group).
- **No raw SQL.** Every figure comes from a named tool (`get_otb_summary`,
  `get_segment_mix`, `get_pickup_delta`, `get_as_of_otb`,
  `get_block_vs_transient_mix`); there is no arbitrary-query path, by design.

When a request collides with a rule, answer the correct way and state the caveat
in one line — that is the discipline, not pedantry.
