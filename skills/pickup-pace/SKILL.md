---
name: pickup-pace
description: "Use when the GM asks what changed recently, booking pace, pickup in the last N days, or how fast a future month is filling. NOT for the static on-the-books total — use monthly-otb-briefing. Calls get_pickup_delta."
---

# Booking pace / pickup

**Do (exact).** `get_pickup_delta(7, today)` for last week and
`get_pickup_delta(30, today)` for last month — it measures business *created* in
the window (`create_datetime`), the leading indicator, not stays occurring in it.
Read `by_segment` to see who is picking up. Compare to the same window last year
by setting `future_stay_from` to the prior-year month.

**Decide:**

| signal | read | action |
|---|---|---|
| weekly run-rate > 120% of monthly run-rate | accelerating | **hold BAR**, **raise rate** on strong dates, add min-LOS on peaks |
| weekly pickup < 50% of needed pace, arrival < 30 days | stalling | open promo/member rates, **drop restrictions** |
| near-zero pickup inside 14 days | at risk | escalate; tactical OTA push to fill, then withdraw |

Judgment: pace tells you where demand is accelerating *before* OTB shows it —
price into strength, discount only into genuine softness.

**Answer like.** "Last 7 days added 17 bookings / £26k for future stays, ahead of
the trailing run-rate and ahead of STLY pace. Demand is strengthening into
Q3 — I'd hold BAR and add a 2-night minimum on the peak weekends rather than
discount."

**Don't** infer pace from stay-date OTB — pickup is by `create_datetime`.
