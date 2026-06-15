---
name: block-concentration
description: "Use when the GM asks about group vs transient, block exposure, key-account/company concentration, displacement risk, or whether a month leans on a few large bookings. NOT for channel/OTA mix — use ota-dependency. Calls get_block_vs_transient_mix."
---

# Block / group concentration

**Do (exact).** `get_block_vs_transient_mix(month)` → read `block_share_of_revenue`,
the block vs transient room-night split, `top_companies`, and
`top3_company_revenue_share`. Compare block share to STLY (same month, year−1).
Cross-check against `get_otb_summary` room nights to see if there is transient
room left to protect.

**Decide:**

| signal | read | action |
|---|---|---|
| `block_share_of_revenue` > 50% | group-heavy | set block **cut-off / wash**, **protect transient** on peaks |
| `block_share_of_revenue` > 65% | very group-led | **review block** ceilings; don't sell below transient BAR around groups |
| `top3_company_revenue_share` > 40% | key-account risk | require deposits / attrition clauses; **hold BAR** for transient |
| single company > 25% of revenue | single-account dependency | escalate; lock contract terms |

Judgment: group is only a problem where the hotel is filling — group on soft
dates is welcome base; group displacing higher-rated transient on peak dates is
the risk.

**Answer like.** "September is 72% block revenue (67% STLY) and the top 3
companies are 78% of the month — concentrated and up year-on-year. I'd set a
30-day cut-off on the largest block and hold BAR for transient on the peak nights."

**Don't** quote room counts as bookings — use room nights and `reservation_count`.
