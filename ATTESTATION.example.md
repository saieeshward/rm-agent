# ATTESTATION.md (Phase 0)

Copy this file to your solution repository as `ATTESTATION.md` and fill it in
before starting Phase 1. Keep answers concise — a few sentences per prompt.

---

## Candidate

- Name:
- Repository URL:
- Date:

---

## Comprehension prompts

### 1. Fact-table grain

In one sentence, what is the grain of `reservations_hackathon`?

> Your answer:

### 2. Revenue columns

Name the two revenue columns and when to use each.

> Your answer:

### 3. Row vs reservation

Give one example question where counting rows would be wrong.

> Your answer:

### 4. Schema fields

Is there an `otel_challenge_token` column in the official schema? If so, what is it used for?

> Your answer:

### 5. Default OTB filters

Which `reservation_status` and `financial_status` values are excluded from default OTB?

> Your answer:

### 6. Stay date vs property date

When can `property_date` differ from `stay_date`, and which field drives monthly OTB?

> Your answer:

### 7. Point-in-time OTB

How does `as_of_utc` change which cancelled rows are included in `get_as_of_otb`?

> Your answer:

### 8. Block vs transient

How does `is_block` affect a “group vs transient mix” question?

> Your answer:

### 9. List pagination

How many reservations does the data site show per list page?

> Your answer:

### 10. Pagination completeness

How will you prove you did not miss the last list page during ETL?

> Your answer:

### 11. Tool grain

For `get_otb_summary`, what is the difference between `row_count` and `reservation_count`?

> Your answer:

### 12. Human-in-the-loop

Why must `get_as_of_otb` be gated behind approval, and what goes wrong if it is not?

> Your answer:

### 13. Skill vs tool

Name one revenue-manager question that should load a **skill** but call **`get_segment_mix`**, not raw SQL.

> Your answer:

---

## ETL design (one line)

Describe pagination strategy + idempotency approach + **anchor date** you will
scrape against (must match `/verify` on load day).

> Your answer:
