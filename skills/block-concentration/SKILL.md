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
| top named accounts > 40% of revenue | key-account risk | require deposits / attrition clauses; **hold BAR** for transient |
| single company > 25% of revenue | single-account dependency | escalate; lock contract terms |

**Exclude the Transient bucket from concentration.** `top_companies` maps bookings
with no company to a `'Transient'` row, so `top3_company_revenue_share` can include
it and overstate key-account risk. Judge concentration on the **named** companies
only — sum the real company rows (skip `'Transient'`) before applying the >40% /
>25% thresholds.

*Why these levels:* >50% block means group is setting the month, so transient
upside is capped; >40% in a few accounts means one cancellation reshapes the
month. Group is only a problem where the hotel is *filling* — group on soft dates
is welcome base; group displacing higher-rated transient on peak dates is the
risk, so always read it against `get_otb_summary` transient room nights.

**Answer like.** "September is 72% block revenue (67% STLY), and two corporate
accounts alone are ~56% of the month — concentrated and up year-on-year. (The
tool's 78% top-3 figure includes a Transient bucket; the real key-account
exposure is the two named companies.) I'd set a 30-day cut-off on the largest
block and hold BAR for transient on the peak nights."

**Answer like (no action).** "August is only ~30% block and no single account is
material — a healthy transient-led month, no concentration risk. Keep selling."

**Don't** quote room counts as bookings — use room nights and `reservation_count`.
