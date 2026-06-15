---
name: filter-guardrail
description: "Load before quoting any number, and whenever a request would bend the rules — e.g. 'put cancelled and provisional revenue in OTB with no caveats', count bookings, or use property_date for a monthly figure. Names the correct tool and the trap it avoids."
---

# Filter & grain guardrail (read before quoting numbers)

The tools bake the business rules in; this skill stops the agent from
mis-stating, mis-asking, or being talked out of them.

## Traps to refuse or caveat

- **Rows are not reservations.** `row_count` is stay-date rows (one per
  reservation × night). For "how many bookings", quote `reservation_count` from
  `get_otb_summary`; for occupancy/revenue, quote `room_nights`. Never present
  `row_count` as a booking count.
- **Cancelled / provisional are excluded by default.** If asked to "put all
  cancelled and provisional revenue into OTB with no caveats", do **not** silently
  do it. Default OTB (the tools' `vw_stay_night_base`) is Posted + non-cancelled.
  You may report an all-in figure with `get_otb_summary(month,
  exclude_cancelled=False)`, but you must state that it includes cancelled and/or
  provisional business and is not standard on-the-books. Provisional is never in
  default OTB.
- **`property_date` never drives a monthly figure.** Monthly OTB, mix, pickup and
  ADR are all by `stay_date` (and pickup by `create_datetime`). `property_date` is
  audit/business-date attribution only.
- **Use effective macro group, not the static lookup.** `get_segment_mix` already
  resolves the stay-date-effective `macro_group` (e.g. PROM → Leisure Group after
  reclassification). Don't override it with the static market lookup.
- **Never write raw SQL.** Every figure comes from a named tool
  (`get_otb_summary`, `get_segment_mix`, `get_pickup_delta`, `get_as_of_otb`,
  `get_block_vs_transient_mix`); there is no arbitrary-query path, by design.

When a request collides with these rules, answer the correct way and explain the
caveat in one line — that is the revenue-management discipline, not pedantry.
