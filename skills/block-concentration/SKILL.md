---
name: block-concentration
description: "Use when the GM asks about group vs transient business, block exposure, key-account/company concentration, displacement risk, or whether a month leans on a few large bookings. Judges block_share_of_revenue and top-account concentration."
---

# Block / group concentration and displacement risk

Call `get_block_vs_transient_mix(stay_month)` and read `block_share_of_revenue`,
the block vs transient room-night split, `top_companies`, and
`top3_company_revenue_share`. Group business is great for base demand but
dangerous when it crowds out higher-rated transient or when it sits in a handful
of accounts that can cancel together.

## Thresholds

- **block_share_of_revenue > 50%** — group-heavy month. Transient displacement
  risk on peak dates: protect transient availability, set a block **cut-off /
  wash** date, and confirm rooming lists before releasing held rooms.
- **block_share_of_revenue > 65%** — very group-led. **Review block** ceilings;
  do not sell remaining inventory below transient BAR just to fill around groups.
- **top3_company_revenue_share > 40%** — key-account concentration. One
  conference moving costs you the month. Diversify the pipeline, require deposits
  / attrition clauses, and **hold BAR** for transient on the same dates.
- **single company > 25%** of month revenue — single-account dependency; escalate
  to the GM and lock the contract terms.

## How to judge, not just report

- Compare block share to the **same month last year** (`get_block_vs_transient_mix`
  on the prior-year month) — a jump means you are trading rate-flexible transient
  for fixed group rate.
- Group displaces transient only where the hotel is filling; line the month up
  against `get_otb_summary` room nights to see if there is room left to protect.
- Name the specific companies driving `top3_company_revenue_share` and the action
  per account (deposit, cut-off, or **review block** size).
