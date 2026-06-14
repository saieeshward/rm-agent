#!/usr/bin/env python3
"""
Phase 1 — TRANSFORM.

Reads the raw scrape snapshot (etl/.cache/raw.json) and produces clean, typed
records matching schema.sql. The fact grain is enforced here: one record per
(reservation_id x stay_date), with reservation-level fields repeated across the
reservation's stay rows and per-night fields taken from the detail stay-rows
table.

Decisions baked in (see ARCHITECTURE.md / ATTESTATION.md):
  - Column whitelist = schema.sql. The detail page's extra `commercial_rate_code`
    (and any honeypot field such as `otel_challenge_token`) is dropped.
  - rate_plan_code is loaded VERBATIM (the commercial code shown on the detail
    page, per the dataset changelog). rate_plan_lookup stays at the 8 canonical
    /reference codes; the rate_plan FK is relaxed at load time because the live
    data uses more granular selling codes than the lookup (Option D).
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

CACHE = Path(__file__).resolve().parent / ".cache"
NULLISH = {"", "—", "-", "–", None}


def _norm(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return None if s in NULLISH else s


def _to_int(v: Any) -> int | None:
    s = _norm(v)
    return None if s is None else int(s.replace(",", ""))


def _to_num(v: Any) -> float | None:
    s = _norm(v)
    return None if s is None else float(s.replace(",", ""))


def _to_bool(v: Any) -> bool:
    return _norm(v) is not None and str(v).strip().lower() == "true"


def _to_date(v: Any) -> date | None:
    s = _norm(v)
    return None if s is None else date.fromisoformat(s[:10])


def _to_dt(v: Any) -> datetime | None:
    s = _norm(v)
    if s is None:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _rows(reference: dict, key: str) -> list[list[str]]:
    block = reference.get(key) or {}
    return block.get("rows") or []


def transform(raw: dict) -> dict[str, list[dict]]:
    reference = raw["reference"]

    room_type_lookup = [
        {"space_type": r[0], "room_class": r[1], "display_name": r[2], "number_of_rooms": _to_int(r[3])}
        for r in _rows(reference, "room_types")
    ]
    rate_plan_lookup = [
        {"rate_plan_code": r[0], "plan_family": r[1], "is_commissionable": _to_bool(r[2])}
        for r in _rows(reference, "rate_plans")
    ]
    market_code_lookup = [
        {"market_code": r[0], "market_name": r[1], "macro_group": r[2], "description": _norm(r[3])}
        for r in _rows(reference, "markets")
    ]
    market_macro_group_history = [
        {"market_code": r[0], "valid_from": _to_date(r[1]), "valid_to": _to_date(r[2]), "macro_group": r[3]}
        for r in _rows(reference, "macro_history")
    ]
    channel_code_lookup = [
        {"channel_code": r[0], "channel_name": r[1], "channel_group": r[2]}
        for r in _rows(reference, "channels")
    ]

    facts: list[dict] = []
    for d in raw["details"]:
        rid = d["reservation_id"]
        f = d["fields"]
        base = {
            "reservation_id": rid,
            "arrival_date": _to_date(f.get("arrival_date")),
            "departure_date": _to_date(f.get("departure_date")),
            "reservation_status": _norm(f.get("reservation_status")),
            "create_datetime": _to_dt(f.get("create_datetime")),
            "cancellation_datetime": _to_dt(f.get("cancellation_datetime")),
            "guest_country": _norm(f.get("guest_country")),
            "is_block": _to_bool(f.get("is_block")),
            "is_walk_in": _to_bool(f.get("is_walk_in")),
            "number_of_spaces": _to_int(f.get("number_of_spaces")),
            "space_type": _norm(f.get("space_type")),
            "market_code": _norm(f.get("market_code")),
            "channel_code": _norm(f.get("channel_code")),
            "source_name": _norm(f.get("source_name")),
            "rate_plan_code": _norm(f.get("rate_plan_code")),  # verbatim (Option D)
            "nights": _to_int(f.get("nights")),
            "adr_room": _to_num(f.get("adr_room")),
            "lead_time": _to_int(f.get("lead_time")),
            "company_name": _norm(f.get("company_name")),
            "travel_agent_name": _norm(f.get("travel_agent_name")),
        }
        headers = [h.strip() for h in d["stay_headers"]]
        for sr in d["stay_rows"]:
            night = dict(zip(headers, sr))
            facts.append({
                **base,
                "stay_date": _to_date(night.get("stay_date")),
                "property_date": _to_date(night.get("property_date")),
                "financial_status": _norm(night.get("financial_status")),
                "daily_room_revenue_before_tax": _to_num(night.get("daily_room_revenue_before_tax")),
                "daily_total_revenue_before_tax": _to_num(night.get("daily_total_revenue_before_tax")),
            })

    return {
        "room_type_lookup": room_type_lookup,
        "rate_plan_lookup": rate_plan_lookup,
        "market_code_lookup": market_code_lookup,
        "market_macro_group_history": market_macro_group_history,
        "channel_code_lookup": channel_code_lookup,
        "reservations_hackathon": facts,
    }


def load_raw(path: Path | None = None) -> dict:
    return json.loads((path or (CACHE / "raw.json")).read_text())


if __name__ == "__main__":
    data = transform(load_raw())
    for table, rows in data.items():
        print(f"{table:32s} {len(rows):>5d} rows")
    facts = data["reservations_hackathon"]
    distinct_res = {r["reservation_id"] for r in facts}
    print(f"\ndistinct reservations: {len(distinct_res)}")
    print(f"financial_status mix : "
          f"{sorted({r['financial_status'] for r in facts})}")
    print(f"reservation_status   : {sorted({r['reservation_status'] for r in facts})}")
