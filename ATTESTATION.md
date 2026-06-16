# ATTESTATION.md (Phase 0)

## Candidate

- Name: Sai Eeshwar Divaakar
- Repository URL: https://github.com/saieeshward/rm-agent
- Live URL: https://otel-rm-agent.onrender.com  (basic auth; credentials shared via the private submission intake)
- Date: 2026-06-16

---

## Comprehension prompts

### 1. Fact-table grain

In one sentence, what is the grain of `reservations_hackathon`?

> One row per reservation per stay date, so a 3-night booking lands as 3 rows, and each row holds its own `number_of_spaces`. That means rows, reservations, and room nights are three different counts.

### 2. Revenue columns

Name the two revenue columns and when to use each.

> `daily_room_revenue_before_tax` is room-only, so I use it for room revenue and ADR. `daily_total_revenue_before_tax` includes packages and extras, so that one is for overall revenue and anything by segment, block, or company. Total is always at least room.

### 3. Row vs reservation

Give one example question where counting rows would be wrong.

> "How many bookings do we have for July?" If you `count(*)` you double-count every multi-night stay. The number the GM actually wants is `count(distinct reservation_id)`.

### 4. Schema fields

Is there an `otel_challenge_token` column in the official schema? If so, what is it used for?

> No. It isn't in `schema.sql` and I never load it. A "scrape everything you see" ETL would happily ingest decoy fields, so my loader only writes the columns that actually exist in `schema.sql` and drops anything extra the detail page shows (e.g. `commercial_rate_code`).

### 5. Default OTB filters

Which `reservation_status` and `financial_status` values are excluded from default OTB?

> Default on-the-books leaves out `reservation_status = 'Cancelled'` and `financial_status = 'Provisional'`, it keeps Posted and non-cancelled only. I baked that into `vw_stay_night_base`, and cancelled or provisional rows come back only when the question asks for them.

### 6. Stay date vs property date

When can `property_date` differ from `stay_date`, and which field drives monthly OTB?

> They drift apart on night-boundary / audit rows (3 of them in this load). Monthly OTB, segment mix and ADR all run off `stay_date`, never `property_date`.

### 7. Point-in-time OTB

How does `as_of_utc` change which cancelled rows are included in `get_as_of_otb`?

> A row only counts if it was already on the books and still alive at that moment: `create_datetime <= as_of_utc`, and either it wasn't cancelled or its `cancellation_datetime` is after `as_of_utc`, and it's Posted. So a reservation cancelled *after* the as-of time still counts (it was live then), one cancelled *before* it does not, and anything booked after the as-of time is excluded.

### 8. Block vs transient

How does `is_block` affect a "group vs transient mix" question?

> `is_block = true` is group/block business and `false` is transient. The mix splits on that flag, and the block and transient room nights add back up to the month's OTB room nights. That's what `get_block_vs_transient_mix` returns.

### 9. List pagination

How many reservations does the data site show per list page?

> 100 per page. The list showed "Page 1 of 3" for 254 reservations.

### 10. Pagination completeness

How will you prove you did not miss the last list page during ETL?

> I read `total_reservations` off `/verify` first, then keep paging until the page indicator reaches the last page. After that I check the distinct `reservation_id` count against both `/verify` and `SCRAPE_MANIFEST.reservation_ids_count`, confirm `reservation_ids_sha256` (sha of the sorted ids) matches the DB, and confirm the load's `reservation_stay_status_sha256` matches `/verify`. It does (`3388ad54…`).

### 11. Tool grain

For `get_otb_summary`, what is the difference between `row_count` and `reservation_count`?

> `row_count` is the stay-date rows in the month (`count(*)`). `reservation_count` is distinct bookings (`count(distinct reservation_id)`). Whenever a booking covers more than one night, `reservation_count` comes out lower than `row_count`.

### 12. Human-in-the-loop

Why must `get_as_of_otb` be gated behind approval, and what goes wrong if it is not?

> It rebuilds the book as it stood at a past instant, which is costly and easy to lean on for a misleading "as of" claim. The approval step lets the GM confirm the snapshot and the intent before it runs. Skip it and the agent can quietly fire off expensive rebuilds, or present a point-in-time number as if it were the current book.

### 13. Skill vs tool

Name one revenue-manager question that should load a **skill** but call **`get_segment_mix`**, not raw SQL.

> "Are we too dependent on OTA?" It loads the `ota-dependency` skill for the thresholds, the STLY comparison and the recommended action, and that skill calls `get_segment_mix` for OTA `share_of_revenue`. The judgment comes from the skill and the numbers come from the tool, with no raw SQL anywhere.

---

## ETL design (one line)

Describe pagination strategy + idempotency approach + **anchor date** you will
scrape against (must match `/verify` on load day).

> Playwright (headless Chromium, assets blocked) walks the client-rendered list 100 at a time and opens each `/reservations/<id>` detail for the `<dl>` fields plus the per-night stay-rows table, run concurrently. The load is idempotent: a single transaction that truncates and reloads (lookups first, then facts, with the rate_plan FK relaxed per Option D) and writes a `load_manifest` row on every run. Anchor date is 2026-06-16 (`dataset_revision 2026.06.12.2`), reconciled against `/verify`. I'll re-scrape and re-check on the actual submit day.
