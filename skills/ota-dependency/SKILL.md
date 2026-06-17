---
name: ota-dependency
description: "Use when the GM asks 'are we too dependent on OTA', about Booking.com/Expedia exposure, commission cost, OTA share, or direct-vs-OTA balance. NOT for overall segment drivers — use segment-mix-shift. Calls get_channel_mix."
---

# OTA dependency

**Grounding (read this first).** OTA is a *channel*, not a market segment. In this
dataset OTA business is the `WEB` channel ("Web / OTA Web", channel_group `Digital`).
`get_segment_mix` only knows market segments (Corporate, Leisure, MICE, Retail …) and
has **no OTA** — never read an "OTA" share from it. Use `get_channel_mix`, which has
the real channel grain.

**Do (exact).** `get_channel_mix(month)` → read `ota_share_of_revenue_pct` (the WEB
channel's share of total revenue). Call `get_channel_mix(STLY_month)` (same month,
year−1) the same way to see whether the share is rising. If the date is high-demand,
confirm with `get_otb_summary` before acting.

**Decide** — OTA `ota_share_of_revenue_pct`:

| share | read | action |
|---|---|---|
| < 15% | under-exposed | safe to lean on OTA in soft months |
| 15–25% | normal | no action; watch the trend vs STLY |
| 25–35% | elevated | **hold BAR**, enforce parity, cap OTA allocation on peaks |
| > 35% | over-dependent | **push direct**, raise OTA-only rates, **close OTA** on compression dates |

*Why ~35%:* OTA costs 15–20% commission, so once it carries a third-plus of
revenue you are renting a large slice of margin on demand you could likely capture
direct. Treat the band as relative, not absolute: high OTA share in a *soft* month
is fine (fill the hotel); the same share in a *strong* month is margin you are
giving away — that is where you act. A rising OTA share on flat total revenue means
you are buying the same business at higher cost.

**Answer like (no action).** "OTA is 17% of July revenue (19% STLY) — modest and
slightly *down* year-on-year, so you're not too dependent; there's headroom to use
OTA tactically in soft weeks. No action on July."

**Answer like (act).** "OTA would be a problem if it looked like this: ~38% of a
*strong* month's revenue. Then I'd push direct (member rates, retargeting), raise
OTA-only rates, and cap or close OTA allocation on the compression dates so
commissionable rooms don't crowd out direct demand."

**Don't** confuse `ota_share_of_revenue_pct` with `ota_share_of_room_nights` — OTA's
room-night share runs higher because it books lower-rated rooms. Quote revenue share
for the dependency call. Never quote an OTA number that did not come from
`get_channel_mix`.
