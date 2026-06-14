#!/usr/bin/env python3
"""
Phase 1 — LOAD.

Idempotent truncate-and-reload of the transformed records into Postgres, in a
single transaction. Anyone can re-run this and get the same database for a given
scrape snapshot.

Order: lookups first (FKs on space_type / market_code / channel_code still
enforced), then the fact table. The rate_plan FK is intentionally relaxed
(Option D): the live data uses more granular selling codes than the 8-row
rate_plan_lookup, and the changelog says the commercial code IS rate_plan_code,
so we keep the true value and drop only that one constraint.

A load_manifest row is appended on every run with row_hash =
reservation_stay_status_sha256 (sha256 of sorted reservation_id|stay_date|
financial_status lines) so it reconciles with /verify and LOAD_PROOF.json.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone

import psycopg

DEFAULT_DATABASE_URL = "postgresql://hackathon:hackathon@localhost:5432/hotel_hackathon"

LOOKUP_ORDER = [
    ("room_type_lookup", ["space_type", "room_class", "display_name", "number_of_rooms"]),
    ("rate_plan_lookup", ["rate_plan_code", "plan_family", "is_commissionable"]),
    ("market_code_lookup", ["market_code", "market_name", "macro_group", "description"]),
    ("market_macro_group_history", ["market_code", "valid_from", "valid_to", "macro_group"]),
    ("channel_code_lookup", ["channel_code", "channel_name", "channel_group"]),
]

FACT_COLS = [
    "reservation_id", "arrival_date", "departure_date", "stay_date", "property_date",
    "reservation_status", "financial_status", "create_datetime", "cancellation_datetime",
    "guest_country", "is_block", "is_walk_in", "number_of_spaces", "space_type",
    "market_code", "channel_code", "source_name", "rate_plan_code",
    "daily_room_revenue_before_tax", "daily_total_revenue_before_tax",
    "nights", "adr_room", "lead_time", "company_name", "travel_agent_name",
]


def reservation_stay_status_sha256(facts: list[dict]) -> str:
    lines = sorted(
        f"{f['reservation_id']}|{f['stay_date'].isoformat()}|{f['financial_status']}"
        for f in facts
    )
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def load(
    data: dict[str, list[dict]],
    *,
    dataset_revision: str,
    source_url: str,
    scraped_at: str | None = None,
    database_url: str | None = None,
) -> dict:
    database_url = database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    facts = data["reservations_hackathon"]
    row_hash = reservation_stay_status_sha256(facts)
    scraped_ts = (
        datetime.fromisoformat(scraped_at.replace("Z", "+00:00"))
        if scraped_at else datetime.now(timezone.utc)
    )

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            # Option D: relax the rate_plan FK; keep all other FKs.
            cur.execute(
                "alter table public.reservations_hackathon "
                "drop constraint if exists reservations_hackathon_rate_plan_code_fkey"
            )
            cur.execute(
                "truncate table "
                "public.reservations_hackathon, public.market_macro_group_history, "
                "public.room_type_lookup, public.rate_plan_lookup, public.market_code_lookup, "
                "public.channel_code_lookup, public.load_manifest "
                "restart identity cascade"
            )

            for table, cols in LOOKUP_ORDER:
                rows = data[table]
                if not rows:
                    continue
                placeholders = ", ".join(["%s"] * len(cols))
                cur.executemany(
                    f"insert into public.{table} ({', '.join(cols)}) values ({placeholders})",
                    [[r.get(c) for c in cols] for r in rows],
                )

            fact_placeholders = ", ".join(["%s"] * len(FACT_COLS))
            cur.executemany(
                f"insert into public.reservations_hackathon ({', '.join(FACT_COLS)}) "
                f"values ({fact_placeholders})",
                [[f.get(c) for c in FACT_COLS] for f in facts],
            )

            cur.execute(
                "insert into public.load_manifest "
                "(dataset_revision, scraped_at, source_url, row_hash) values (%s, %s, %s, %s)",
                (dataset_revision, scraped_ts, source_url, row_hash),
            )
        conn.commit()

    return {
        "row_hash": row_hash,
        "fact_rows": len(facts),
        "dataset_revision": dataset_revision,
        "scraped_at": scraped_ts.isoformat(),
    }


if __name__ == "__main__":
    # Manual run against the cached snapshot for development.
    from transform import load_raw, transform

    raw = load_raw()
    result = load(
        transform(raw),
        dataset_revision=raw["verify"]["dataset_revision"],
        source_url=raw["base_url"],
        scraped_at=raw["verify"].get("anchor_date"),
    )
    print(result)
