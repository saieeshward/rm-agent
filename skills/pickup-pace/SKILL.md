---
name: pickup-pace
description: "Use when the GM asks what changed recently, booking pace, pickup in the last N days, or how fast a future month is filling. Judges recent create_datetime pickup against pace and recommends a rate/restriction move."
---

# Booking pace / pickup

Call `get_pickup_delta(booking_window_days, future_stay_from)` — it measures
business **created** in the window (by `create_datetime`), not stays occurring in
it. Use 7 for "last week", 30 for "last month". Pickup is the leading indicator:
it tells you where demand is accelerating *before* it shows up in OTB.

## How to judge

- Run `get_pickup_delta(7, today)` and `get_pickup_delta(30, today)`; compare the
  weekly run-rate (7-day ÷ 1) to the monthly run-rate (30-day ÷ 4.3). Accelerating
  weekly pickup = demand strengthening; decelerating = softening.
- Anchor to pace: compare picked-up room nights against the same window **last
  year** (run pickup with `future_stay_from` set to the prior-year month). Ahead
  of STLY pace = pricing power; behind = a gap to close.
- Read `by_segment` to see *who* is picking up — group vs retail vs OTA changes
  the action.

## Thresholds and actions

- **Weekly pickup > 120% of the trailing run-rate** for a near month — demand is
  outpacing pace. **Hold BAR**, raise rate on the strong dates, and add minimum
  length-of-stay on peak nights.
- **Weekly pickup < 50% of run-rate** with arrival inside ~30 days — pace is
  stalling. Open promotional rates / member offers and drop length-of-stay
  restrictions to convert the remaining window.
- **Near-zero pickup** (< 5% of needed pace) inside 14 days — escalate; consider a
  tactical OTA push purely to fill, then withdraw it.

Always pull pickup from `get_pickup_delta`; do not infer pace from stay-date OTB.
