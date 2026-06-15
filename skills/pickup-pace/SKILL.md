---
name: pickup-pace
description: "Use when the GM asks what changed recently, booking pace, pickup in the last N days, how fast a month is filling, or whether demand is ahead/behind. NOT for the static on-the-books total — use monthly-otb-briefing. Calls get_pickup_delta and get_booking_pace."
---

# Booking pace / pickup

Two complementary reads: **recent pickup** (what arrived this week) and the
**booking curve** (how far ahead the month is booking vs last year). Pace is the
leading indicator — price into strength, discount only into genuine softness.

**Do (exact).**
1. `get_pickup_delta(7, today)` and `get_pickup_delta(30, today)` — business
   *created* in the window (`create_datetime`), not stays occurring in it. Read
   `by_segment` for who is picking up.
2. `get_booking_pace(month)` and `get_booking_pace(<same month, year-1>)` — compare
   the curve: `avg_lead_time` and `share_booked_90plus` vs `share_under_30`.

**Decide.**

| signal | read | action |
|---|---|---|
| weekly run-rate > 120% of monthly run-rate | accelerating | **hold BAR**, **raise rate** on strong dates, add min-LOS on peaks |
| `share_under_30` materially above STLY (e.g. +10 pts) | booking later than the curve — softness/late-demand | open promo/member rates, **drop restrictions** early |
| `share_booked_90plus` above STLY with healthy volume | strong advance demand | **hold BAR**, push rate; you have pricing power |
| near-zero 7-day pickup inside 14 days of arrival | at risk | escalate; tactical OTA push to fill, then withdraw |

*Why curve-vs-STLY, not an absolute number:* "good pace" is only meaningful
relative to how this month normally books and how much lead time it carries — a
group month legitimately books 100+ days out, a transient weekend books inside 30.
STLY at the same point is the honest yardstick.

**Answer like (strong).** "July is booking *ahead* of the curve — 72% of room
nights are already booked 90+ days out vs 34% this time last year, and last week
added 17 bookings. That's advance-demand strength, not a fluke; I'd hold BAR and
add a 2-night minimum on the peak weekends rather than discount."

**Answer like (soft).** "October's pace has slipped — `share_under_30` is well
above STLY and weekly pickup is thin with arrivals inside a month. I'd open a
member/promo rate and drop the length-of-stay restrictions to convert the window
before it's too late."

**Don't** infer pace from stay-date OTB — pickup is by `create_datetime`, the
curve by `lead_time`.
