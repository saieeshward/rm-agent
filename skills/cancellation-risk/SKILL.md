---
name: cancellation-risk
description: "Use when the GM asks how much was cancelled, attrition, wash, or how firm the book is. NOT for current on-the-books (use monthly-otb-briefing). Calls get_otb_summary (exclude_cancelled toggle) and get_as_of_otb."
---

# Cancellation risk / attrition

**Do (exact).** Cancelled share: `get_otb_summary(month, exclude_cancelled=False)`
minus the default `get_otb_summary(month)` — the difference is the cancelled
(Posted) business; report it as a % of the all-in total. Attrition over time:
`get_as_of_otb(month, earlier_utc)` vs today's OTB — a higher past figure means
business has washed out since.

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

**Don't** present cancelled figures as on-the-books — default OTB excludes
cancelled and provisional; always flag when a number includes them.
