---
name: cancellation-risk
description: "Use when the GM asks how much was cancelled, attrition, wash, or how firm the book is. NOT for current on-the-books (use monthly-otb-briefing). Calls get_cancellation_summary, with get_as_of_otb vs get_otb_summary for attrition over time."
---

# Cancellation risk / attrition

**Do (exact).** Cancelled share: call `get_cancellation_summary(month)` — it returns
`cancelled_revenue`, `all_in_revenue` and `cancelled_share_of_revenue(_pct)` already
computed (never subtract two OTB calls yourself). Attrition over time:
`get_as_of_otb(month, earlier_utc)` vs today's `get_otb_summary(month)` — a higher
past figure means business has washed out since.

**Decide:**

| signal | read | action |
|---|---|---|
| cancelled > 12% of revenue | soft book | **require deposits** / non-refundable on those dates; controlled overbook on peaks |
| cancelled > 20% | high wash | move new bookings to non-refundable; **review block** attrition clauses |
| as-of OTB today < as-of 30 days ago | active wash | protect rate, don't chase lost rooms with discounts |

Judgment: a little cancellation is normal churn; a rising cancelled share
concentrated on specific dates is a policy problem, not a demand problem.

**Answer like.** "June cancelled business is ~3% of the all-in total — well within
normal churn, no action. (Figure includes cancelled rows; standard on-the-books
excludes them.)"

**Answer like (act).** "August is washing — cancelled business is ~15% of the
all-in total and the as-of book 30 days ago was higher than today. I'd move new
bookings on the peak dates to non-refundable, take deposits, and overbook the
strongest nights to cover expected wash."

**Don't** present cancelled figures as on-the-books — default OTB excludes
cancelled and provisional; always flag when a number includes them.
