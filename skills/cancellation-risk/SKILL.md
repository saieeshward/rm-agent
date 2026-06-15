---
name: cancellation-risk
description: "Use when the GM asks how much business was cancelled, attrition, wash, or how firm the book is. Judges the cancelled share of a month and how the on-the-books figure has eroded over time, and recommends a policy move."
---

# Cancellation risk / attrition

Two reads: the **cancelled share** of a month, and how the book has **eroded over
time**.

- Cancelled share: compare `get_otb_summary(month, exclude_cancelled=False)` with
  the default `get_otb_summary(month)`. The difference is the cancelled
  (Posted) business in that month — report it as a % of the
  exclude_cancelled=False total revenue.
- Attrition over time: use `get_as_of_otb(month, as_of_utc)` at an earlier instant
  vs the current OTB. A point-in-time figure that was higher than today means
  bookings have washed out since.

## Thresholds and actions

- **Cancelled share > 12% of revenue** for a month — the book is soft. Tighten
  terms: require deposits or non-refundable rates on the affected dates, and
  consider controlled overbooking on high-demand nights to offset expected wash.
- **Cancelled share > 20%** — escalate; move new bookings on those dates to
  non-refundable and **review block** attrition clauses for group business.
- **As-of OTB today < as-of OTB 30 days ago** for a future month — active wash;
  flag the pace reversal and protect rate rather than chasing the lost rooms with
  discounts.

Default OTB already excludes cancelled and provisional business; only surface
cancelled figures when the GM asks about cancellations, and always say the number
includes cancelled rows so it isn't confused with on-the-books.
