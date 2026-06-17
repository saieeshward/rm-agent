# Metric definitions

How the tool layer defines every metric it returns. The five required tools (plus
the supplementary `get_adr_by_room_type`) read **semantic views only**, never
`reservations_hackathon` directly, and never accept free-form SQL.

## Grain — rows vs reservations vs room nights

The fact table is **one row per `reservation_id` × `stay_date`** (a 3-night booking
is 3 rows; a 2-room booking carries `number_of_spaces = 2` on each of those rows).
So three different counts are *not* interchangeable:

| Metric | Definition |
|--------|------------|
| `row_count` | stay-date rows in scope (`count(*)`) |
| `reservation_count` | distinct bookings (`count(distinct reservation_id)`) |
| `room_nights` | rooms occupied across nights (`sum(number_of_spaces)`) |

For any month `reservation_count ≤ row_count` and `room_nights ≥ row_count` when any
booking has more than one room. Counting rows as bookings is the classic error this
layer prevents.

## Default OTB filters

The **default on-the-books universe** is `vw_stay_night_base`:

- exclude `reservation_status = 'Cancelled'`
- exclude `financial_status = 'Provisional'` (Posted only)

`get_otb_summary(exclude_cancelled=False)` and `get_as_of_otb` read
`vw_stay_night_posted` (Posted, **cancelled included**) — the only paths that need
cancelled rows. Provisional stays are never in default OTB; include them only when a
question explicitly asks for tentative/uncommitted business.

**Anchor date / forward OTB cut.** "On the books" is forward-looking: the default
current-book tools (`get_otb_summary`, `get_segment_mix`, `get_block_vs_transient_mix`,
`get_adr_by_room_type`, and the *current* side of `get_otb_comparison`) restrict to
`stay_date >= anchor`, where the anchor is read from `load_manifest.scraped_at` — **not**
the wall clock, so it stays fixed for the frozen load and matches `/verify`'s
`stay_date >= current_date` oracle (`sql/queries.sql`). Effect by month: a future month
is unchanged; the current month drops already-stayed nights; a fully past month returns
~nothing (its book is closed). Every cut tool exposes `future_only=False` to recover a
past month's actuals. Tools that need history or a point in time deliberately do NOT cut:
the **STLY side** of `get_otb_comparison` (last year is entirely past — a cut would zero
it), `get_booking_pace` (lead-time curve over the full month, compared to STLY),
`get_cancellation_summary`, and `get_as_of_otb` (its own `create/cancellation` time logic).

## Revenue columns

- `room_revenue` = `sum(daily_room_revenue_before_tax)` — room only.
- `total_revenue` = `sum(daily_total_revenue_before_tax)` — room + packages, so
  `total_revenue ≥ room_revenue`. Segment / block / company revenue uses
  `total_revenue`.

## Dates

| Field | Used for | Tool(s) |
|-------|----------|---------|
| `stay_date` | monthly OTB, segment/block mix | otb, segment, block, adr |
| `create_datetime` (UTC) | booking pace / pickup window | pickup |
| `cancellation_datetime` | point-in-time liveness | as_of |
| `property_date` | hotel business-date attribution only — **never** drives monthly OTB | — |

## Pickup window (`get_pickup_delta`)

`booking_window_days` is interpreted on **`create_datetime`** (booking time), not
`stay_date`. The window is `[start_of_day_Europe/London(now − days), now]`, converted
to **UTC** for comparison (timestamps are stored in UTC). `future_stay_from` then
restricts to `stay_date >= that date`.

## Effective macro group (`get_segment_mix`)

`macro_group` is **effective-dated**. `vw_segment_stay_night` resolves it against
`market_macro_group_history` on `stay_date` (`valid_from <= stay_date < valid_to`),
falling back to the static `market_code_lookup.macro_group` only when no history row
matches. Example: `PROM` is `Retail` before 2025-06-01 and `Leisure Group` after — so
the static lookup alone would misclassify post-cutoff PROM stays.

## Segment shares (`get_segment_mix`)

`share_of_room_nights` and `share_of_revenue` are in `[0, 1]` and use a **single shared
denominator** = the total over all segments in scope. With `macro_group` set, scope
narrows to that effective group (shares then sum to 1 within it). The denominators are
echoed in the payload.

## ADR (`get_adr_by_room_type`, supplementary)

- `adr_room_avg` = `avg(adr_room)` over **distinct reservations** (the reservation-level
  rate; matches `/verify`'s `adr_by_room_type`).
- `revenue_per_room_night` = `sum(daily_room_revenue_before_tax) / sum(number_of_spaces)`
  (realised rate per room-night).

## Booking pace / lead time (`get_booking_pace`, supplementary)

`lead_time` = days between booking creation and arrival. `get_booking_pace`
profiles a month's OTB by room-night-weighted lead-time buckets
(`share_booked_90plus`, `share_60_89`, `share_30_59`, `share_under_30`, summing to
1) plus a room-night-weighted `avg_lead_time`. Judge it **against the same month
last year** (the booking curve): more `share_under_30` than STLY = booking later
(softness/short-lead); more `share_booked_90plus` = strong advance demand. This is
the real revenue-management pace read, beyond raw pickup.

## Note — `rate_plan_code` (Option D)

The live data uses more granular commercial rate codes (16 distinct) than the 8-row
`rate_plan_lookup`, and the changelog says the commercial code *is* `rate_plan_code`.
We load it verbatim, keep the lookup at 8, and relax that one FK at load time. No tool
reads `rate_plan_code`, so this does not affect any metric above. See `ARCHITECTURE.md`.
