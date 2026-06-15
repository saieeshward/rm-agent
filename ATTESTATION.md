# ATTESTATION.md (Phase 0)

## Candidate

- Name: EESH-843
- Repository URL: https://github.com/saieeshward/otel-rm-agent
- Date: 2026-06-15

---

## Comprehension prompts

### 1. Fact-table grain

In one sentence, what is the grain of `reservations_hackathon`?

> One row per **reservation × stay_date** (a 3-night booking produces 3 rows), with
> `number_of_spaces` carrying the room count on each row — so rows ≠ reservations ≠ room nights.

### 2. Revenue columns

Name the two revenue columns and when to use each.

> `daily_room_revenue_before_tax` = room-only revenue (use for room-revenue/ADR questions);
> `daily_total_revenue_before_tax` = room + packages/extras (use for overall revenue and segment/
> block/company revenue). `total ≥ room` always.

### 3. Row vs reservation

Give one example question where counting rows would be wrong.

> "How many bookings do we have for July?" — counting rows over-counts multi-night stays;
> the answer is `count(distinct reservation_id)`, not `count(*)`.

### 4. Schema fields

Is there an `otel_challenge_token` column in the official schema? If so, what is it used for?

> No. There is no `otel_challenge_token` column in `schema.sql`, and we do not load one. It is a
> honeypot: a naive "scrape-everything" ETL would ingest extra/decoy fields. We whitelist exactly the
> `schema.sql` columns and drop any extra field the detail page shows (e.g. `commercial_rate_code`).

### 5. Default OTB filters

Which `reservation_status` and `financial_status` values are excluded from default OTB?

> Default on-the-books excludes `reservation_status = 'Cancelled'` and `financial_status = 'Provisional'`
> (i.e. Posted + non-cancelled). Baked into `vw_stay_night_base`. Cancelled/provisional are included only
> on explicit request.

### 6. Stay date vs property date

When can `property_date` differ from `stay_date`, and which field drives monthly OTB?

> `property_date` (hotel business date) can differ from `stay_date` on night-boundary/audit rows (3 such
> rows in this load). Monthly OTB, segment mix and ADR are driven by **`stay_date`** — never `property_date`.

### 7. Point-in-time OTB

How does `as_of_utc` change which cancelled rows are included in `get_as_of_otb`?

> A row counts only if it was already booked and still live at that instant: `create_datetime <= as_of_utc`
> AND (`reservation_status <> 'Cancelled'` OR `cancellation_datetime > as_of_utc`) AND Posted. So a
> reservation cancelled *after* `as_of_utc` is still counted (it was on the books then); one cancelled
> *before* it is excluded; bookings created after it are excluded.

### 8. Block vs transient

How does `is_block` affect a "group vs transient mix" question?

> `is_block = true` is group/block business, `false` is transient. The mix splits on `is_block`; block +
> transient room nights reconcile to the month's OTB room nights. Used by `get_block_vs_transient_mix`.

### 9. List pagination

How many reservations does the data site show per list page?

> 100 per page (the list showed "Page 1 of 3" for 254 reservations).

### 10. Pagination completeness

How will you prove you did not miss the last list page during ETL?

> Read `total_reservations` from `/verify` up front, page through the list until the page indicator reaches
> its last page, then assert collected `count(distinct reservation_id)` equals `/verify` and equals
> `SCRAPE_MANIFEST.reservation_ids_count`. `reservation_ids_sha256` (sha of sorted ids) must match the DB,
> and the load's `reservation_stay_status_sha256` must match `/verify` — which it does (`da950a13…`).

### 11. Tool grain

For `get_otb_summary`, what is the difference between `row_count` and `reservation_count`?

> `row_count` = stay-date rows in the month (`count(*)`); `reservation_count` = distinct bookings
> (`count(distinct reservation_id)`). `reservation_count < row_count` whenever any booking spans
> multiple nights.

### 12. Human-in-the-loop

Why must `get_as_of_otb` be gated behind approval, and what goes wrong if it is not?

> It is an expensive point-in-time rebuild (re-derives the book as known at a past instant) and is easy to
> misuse for misleading "as of" claims. Gating it behind an approval interrupt lets the GM confirm the
> as-of moment and intent. Ungated, the agent could silently run costly snapshots or present a point-in-time
> figure as if it were current OTB.

### 13. Skill vs tool

Name one revenue-manager question that should load a **skill** but call **`get_segment_mix`**, not raw SQL.

> "Are we too dependent on OTA?" — loads the `ota-dependency` skill (thresholds, STLY comparison,
> recommended action) which calls `get_segment_mix` for OTA `share_of_revenue`. The skill supplies the
> judgment; the tool supplies the correct, filtered numbers — no raw SQL.

---

## ETL design (one line)

Describe pagination strategy + idempotency approach + **anchor date** you will
scrape against (must match `/verify` on load day).

> Playwright (headless Chromium, assets blocked) pages the client-rendered list 100/page and drills into
> each `/reservations/<id>` detail (`<dl>` fields + per-night stay-rows table), concurrently; load is an
> idempotent single-transaction truncate-and-reload (lookups→facts; the rate_plan FK is relaxed per Option
> D) with a `load_manifest` row each run. Anchor date **2026-06-14** (`dataset_revision 2026.06.12.2`),
> reconciled against `/verify` — re-scrape and re-reconcile on the actual submit day.
