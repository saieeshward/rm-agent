"""
The five required Revenue Manager tools (Phase 2).

Design rules (REQUIRED_TOOLS.md):
  - Each tool reads a SEMANTIC VIEW, never reservations_hackathon directly.
  - No tool accepts a free-form SQL string. Arguments are typed and validated.
  - Default OTB universe excludes reservation_status='Cancelled' AND
    financial_status='Provisional' (baked into vw_stay_night_base).
  - Grain definitions (stated again in tools/METRIC_DEFINITIONS.md):
      * row_count          = stay-date rows           (one row per reservation x stay_date)
      * reservation_count  = count(distinct reservation_id)
      * room_nights        = sum(number_of_spaces)    (a multi-room booking adds >1 per night)

Views used:
  vw_stay_night_base    Posted + non-cancelled            (default OTB)
  vw_stay_night_posted  Posted, cancelled included        (exclude_cancelled=False / as-of)
  vw_segment_stay_night base + market_name + effective_macro_group
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .db import query, query_one

LONDON = ZoneInfo("Europe/London")
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_BASE_VIEWS = {"base": "vw_stay_night_base", "posted": "vw_stay_night_posted"}


# --------------------------------------------------------------------------- #
# validation / coercion helpers
# --------------------------------------------------------------------------- #
def _month_range(stay_month: Any) -> tuple[date, date]:
    """Return [first_of_month, first_of_next_month) for a 'YYYY-MM' string."""
    if not isinstance(stay_month, str) or not _MONTH_RE.match(stay_month.strip()):
        raise ValueError(f"stay_month must be 'YYYY-MM' (e.g. '2026-07'); got {stay_month!r}")
    y, m = (int(p) for p in stay_month.strip().split("-"))
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return start, end


def _parse_date(value: Any, field: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date 'YYYY-MM-DD'; got {value!r}")
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date 'YYYY-MM-DD'; got {value!r}") from exc


def _parse_utc(value: Any, field: str = "as_of_utc") -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 timestamp; got {value!r}")
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp; got {value!r}") from exc
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "n", "")
    return bool(value)


def _i(x: Any) -> int:
    return int(x) if x is not None else 0


def _f(x: Any) -> float:
    return float(x) if x is not None else 0.0


def _money(x: Any) -> float:
    return round(_f(x), 2)


def _share(part: Any, whole: float) -> float:
    return (_f(part) / whole) if whole else 0.0


def _agg(sql: str, params: tuple | list) -> dict[str, Any]:
    """query_one for an aggregate SELECT (always one row); never None."""
    return query_one(sql, params) or {}


# --------------------------------------------------------------------------- #
# 1. get_otb_summary
# --------------------------------------------------------------------------- #
def get_otb_summary(stay_month: str, exclude_cancelled: bool = True) -> dict:
    """
    On-the-books summary for a calendar month of stay dates (YYYY-MM).

    Grain: aggregates stay-date rows. row_count is NOT reservation_count.
      - row_count          stay-date rows in the month
      - reservation_count  distinct reservation_id
      - room_nights        sum(number_of_spaces)  (rooms x nights)
      - room_revenue       sum(daily_room_revenue_before_tax)
      - total_revenue      sum(daily_total_revenue_before_tax)  (>= room_revenue)

    Default universe vw_stay_night_base (Posted, non-cancelled). exclude_cancelled=False
    switches to vw_stay_night_posted (cancelled included; provisional still excluded).
    """
    start, end = _month_range(stay_month)
    keep = _as_bool(exclude_cancelled)
    view = _BASE_VIEWS["base"] if keep else _BASE_VIEWS["posted"]
    row = _agg(
        f"""
        select
          count(*)                                              as row_count,
          count(distinct reservation_id)                        as reservation_count,
          coalesce(sum(number_of_spaces), 0)                    as room_nights,
          coalesce(sum(daily_room_revenue_before_tax), 0)       as room_revenue,
          coalesce(sum(daily_total_revenue_before_tax), 0)      as total_revenue
        from public.{view}
        where stay_date >= %s and stay_date < %s
        """,
        (start, end),
    )
    return {
        "stay_month": stay_month,
        "row_count": _i(row.get("row_count")),
        "reservation_count": _i(row.get("reservation_count")),
        "room_nights": _i(row.get("room_nights")),
        "room_revenue": _money(row.get("room_revenue")),
        "total_revenue": _money(row.get("total_revenue")),
        "exclude_cancelled": keep,
    }


# --------------------------------------------------------------------------- #
# 2. get_segment_mix
# --------------------------------------------------------------------------- #
def get_segment_mix(stay_month: str, macro_group: str | None = None) -> dict:
    """
    Segment mix for a stay month using vw_segment_stay_night (effective macro_group).

    Grain: stay-date rows grouped by market. room_nights = sum(number_of_spaces),
    total_revenue = sum(daily_total_revenue_before_tax). Shares are 0-1 and use a
    SINGLE shared denominator = the total over all segments in scope; if macro_group
    is given, scope is restricted to that effective macro_group (shares then sum to
    1 within it). The denominator is echoed in the payload.
    """
    start, end = _month_range(stay_month)
    where = "stay_date >= %s and stay_date < %s"
    params: list[Any] = [start, end]
    if macro_group not in (None, ""):
        where += " and lower(effective_macro_group) = lower(%s)"
        params.append(macro_group)

    rows = query(
        f"""
        select
          market_code,
          market_name,
          effective_macro_group                            as macro_group,
          coalesce(sum(number_of_spaces), 0)               as room_nights,
          coalesce(sum(daily_total_revenue_before_tax), 0) as total_revenue
        from public.vw_segment_stay_night
        where {where}
        group by market_code, market_name, effective_macro_group
        order by total_revenue desc, room_nights desc, market_code
        """,
        params,
    )

    denom_rn = float(sum(_i(r["room_nights"]) for r in rows))
    denom_rev = float(sum(_f(r["total_revenue"]) for r in rows))
    segments = [
        {
            "market_code": r["market_code"],
            "market_name": r["market_name"],
            "macro_group": r["macro_group"],
            "room_nights": _i(r["room_nights"]),
            "total_revenue": _money(r["total_revenue"]),
            "share_of_room_nights": _share(r["room_nights"], denom_rn),
            "share_of_revenue": _share(r["total_revenue"], denom_rev),
        }
        for r in rows
    ]
    return {
        "stay_month": stay_month,
        "macro_group": macro_group if macro_group not in (None, "") else None,
        "segment_count": len(segments),
        "denominator_room_nights": int(denom_rn),
        "denominator_revenue": round(denom_rev, 2),
        "segments": segments,
    }


# --------------------------------------------------------------------------- #
# 3. get_pickup_delta
# --------------------------------------------------------------------------- #
def get_pickup_delta(booking_window_days: int, future_stay_from: str) -> dict:
    """
    Booking pace / pickup: business CREATED recently for future stays.

    The window is defined on create_datetime (the BOOKING date), NOT stay_date:
      [start_of_day_London(now - booking_window_days), now], compared in UTC.
    future_stay_from filters to stay_date >= that ISO date.

    Grain: new_reservations = distinct reservation_id created in the window;
    new_room_nights = sum(number_of_spaces) of their qualifying stay rows;
    new_total_revenue = sum(daily_total_revenue_before_tax). by_segment breaks the
    same metrics down by market, ordered by revenue desc.
    """
    days = int(booking_window_days)
    if days < 0:
        raise ValueError(f"booking_window_days must be >= 0; got {booking_window_days!r}")
    stay_from = _parse_date(future_stay_from, "future_stay_from")

    now_utc = datetime.now(timezone.utc)
    start_london = (now_utc.astimezone(LONDON) - timedelta(days=days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start_utc = start_london.astimezone(timezone.utc)
    params = (start_utc, now_utc, stay_from)

    totals = _agg(
        """
        select
          count(distinct reservation_id)                   as new_reservations,
          coalesce(sum(number_of_spaces), 0)               as new_room_nights,
          coalesce(sum(daily_total_revenue_before_tax), 0) as new_total_revenue
        from public.vw_stay_night_base
        where create_datetime >= %s and create_datetime <= %s and stay_date >= %s
        """,
        params,
    )
    by_segment = query(
        """
        select
          market_code,
          count(distinct reservation_id)                   as new_reservations,
          coalesce(sum(number_of_spaces), 0)               as new_room_nights,
          coalesce(sum(daily_total_revenue_before_tax), 0) as new_total_revenue
        from public.vw_stay_night_base
        where create_datetime >= %s and create_datetime <= %s and stay_date >= %s
        group by market_code
        order by new_total_revenue desc, market_code
        """,
        params,
    )
    return {
        "booking_window_days": days,
        "future_stay_from": stay_from.isoformat(),
        "window_start_utc": start_utc.isoformat(),
        "window_end_utc": now_utc.isoformat(),
        "new_reservations": _i(totals.get("new_reservations")),
        "new_room_nights": _i(totals.get("new_room_nights")),
        "new_total_revenue": _money(totals.get("new_total_revenue")),
        "by_segment": [
            {
                "market_code": s["market_code"],
                "new_reservations": _i(s["new_reservations"]),
                "new_room_nights": _i(s["new_room_nights"]),
                "new_total_revenue": _money(s["new_total_revenue"]),
            }
            for s in by_segment
        ],
    }


# --------------------------------------------------------------------------- #
# 4. get_as_of_otb  (gate behind human-in-the-loop in the agent)
# --------------------------------------------------------------------------- #
def get_as_of_otb(stay_month: str, as_of_utc: str) -> dict:
    """
    Point-in-time on-the-books for a stay month as known at as_of_utc.

    A stay row counts when, at that UTC instant, it was already booked and still
    live and posted:
      - create_datetime <= as_of_utc
      - and (reservation_status <> 'Cancelled' OR cancellation_datetime > as_of_utc)
      - and financial_status = 'Posted'  (via vw_stay_night_posted)

    Same grain/shape as get_otb_summary (row_count != reservation_count;
    room_nights = sum(number_of_spaces)), plus an as_of_utc echo.
    """
    start, end = _month_range(stay_month)
    as_of = _parse_utc(as_of_utc)
    row = _agg(
        """
        select
          count(*)                                          as row_count,
          count(distinct reservation_id)                    as reservation_count,
          coalesce(sum(number_of_spaces), 0)                as room_nights,
          coalesce(sum(daily_room_revenue_before_tax), 0)   as room_revenue,
          coalesce(sum(daily_total_revenue_before_tax), 0)  as total_revenue
        from public.vw_stay_night_posted
        where stay_date >= %s and stay_date < %s
          and create_datetime <= %s
          and (reservation_status <> 'Cancelled' or cancellation_datetime > %s)
        """,
        (start, end, as_of, as_of),
    )
    return {
        "stay_month": stay_month,
        "as_of_utc": as_of.isoformat(),
        "row_count": _i(row.get("row_count")),
        "reservation_count": _i(row.get("reservation_count")),
        "room_nights": _i(row.get("room_nights")),
        "room_revenue": _money(row.get("room_revenue")),
        "total_revenue": _money(row.get("total_revenue")),
    }


# --------------------------------------------------------------------------- #
# 5. get_block_vs_transient_mix
# --------------------------------------------------------------------------- #
def get_block_vs_transient_mix(stay_month: str) -> dict:
    """
    Block (group) vs transient mix for a stay month (vw_stay_night_base).

    Grain: stay-date rows split on is_block. room_nights = sum(number_of_spaces).
    block_room_nights + transient_room_nights reconciles to the month's OTB room
    nights from get_otb_summary. Shares are 0-1. top_companies are the top 3
    company_name by revenue (NULL company -> 'Transient'); top3_company_revenue_share
    is their combined share of the month's total revenue (<= 1).
    """
    start, end = _month_range(stay_month)
    agg = _agg(
        """
        select
          coalesce(sum(number_of_spaces) filter (where is_block), 0)                    as block_room_nights,
          coalesce(sum(number_of_spaces) filter (where not is_block), 0)                as transient_room_nights,
          coalesce(sum(daily_total_revenue_before_tax) filter (where is_block), 0)      as block_total_revenue,
          coalesce(sum(daily_total_revenue_before_tax) filter (where not is_block), 0)  as transient_total_revenue,
          coalesce(sum(daily_total_revenue_before_tax), 0)                              as month_total_revenue
        from public.vw_stay_night_base
        where stay_date >= %s and stay_date < %s
        """,
        (start, end),
    )
    companies = query(
        """
        select
          coalesce(company_name, 'Transient')              as company,
          coalesce(sum(daily_total_revenue_before_tax), 0) as revenue,
          coalesce(sum(number_of_spaces), 0)               as room_nights
        from public.vw_stay_night_base
        where stay_date >= %s and stay_date < %s
        group by coalesce(company_name, 'Transient')
        order by revenue desc, company
        limit 3
        """,
        (start, end),
    )

    block_rn = _i(agg.get("block_room_nights"))
    trans_rn = _i(agg.get("transient_room_nights"))
    total_rn = float(block_rn + trans_rn)
    total_rev = _f(agg.get("month_total_revenue"))
    top3_rev = sum(_f(c["revenue"]) for c in companies)
    return {
        "stay_month": stay_month,
        "block_room_nights": block_rn,
        "transient_room_nights": trans_rn,
        "block_total_revenue": _money(agg.get("block_total_revenue")),
        "transient_total_revenue": _money(agg.get("transient_total_revenue")),
        "block_share_of_room_nights": _share(block_rn, total_rn),
        "block_share_of_revenue": _share(agg.get("block_total_revenue"), total_rev),
        "top_companies": [
            {
                "company": c["company"],
                "total_revenue": _money(c["revenue"]),
                "room_nights": _i(c["room_nights"]),
            }
            for c in companies
        ],
        "top3_company_revenue_share": _share(top3_rev, total_rev),
    }


# --------------------------------------------------------------------------- #
# 6. get_adr_by_room_type  (supplementary; answers "highest ADR room type")
# --------------------------------------------------------------------------- #
def get_adr_by_room_type(stay_month: str | None = None) -> dict:
    """
    ADR by room type for the OTB universe (vw_stay_night_base), joined to
    room_type_lookup for human names. Supplementary to the five required tools.

    Grain: aggregates by space_type. Two ADR notions are returned because the
    dataset carries both:
      - adr_room_avg            = avg(adr_room) over DISTINCT reservations
                                  (the reservation-level rate; matches /verify's
                                  adr_by_room_type definition)
      - revenue_per_room_night  = sum(daily_room_revenue_before_tax)
                                  / sum(number_of_spaces)  (realised ADR/room-night)
    Also returns reservation_count (distinct) and room_nights (sum number_of_spaces).
    Pass stay_month='YYYY-MM' to scope to a month; omit for all OTB. Ordered by
    adr_room_avg descending so the highest-ADR room type is first.
    """
    month_filter = ""
    params: list[Any] = []
    if stay_month not in (None, ""):
        start, end = _month_range(stay_month)
        month_filter = "where stay_date >= %s and stay_date < %s"
        params = [start, end]

    # adr_room_avg is averaged over DISTINCT reservations (reservation-level rate),
    # while room_nights / room_revenue are summed over stay rows: two grains.
    rows = query(
        f"""
        with res as (
          select distinct reservation_id, space_type, adr_room
          from public.vw_stay_night_base {month_filter}
        ),
        nights as (
          select space_type,
                 count(distinct reservation_id)                   as reservation_count,
                 coalesce(sum(number_of_spaces), 0)               as room_nights,
                 coalesce(sum(daily_room_revenue_before_tax), 0)  as room_revenue
          from public.vw_stay_night_base {month_filter}
          group by space_type
        )
        select n.space_type, rt.room_class, rt.display_name,
               n.reservation_count, n.room_nights, n.room_revenue,
               round(avg(r.adr_room), 2) as adr_room_avg
        from nights n
        join public.room_type_lookup rt on rt.space_type = n.space_type
        join res r on r.space_type = n.space_type
        group by n.space_type, rt.room_class, rt.display_name,
                 n.reservation_count, n.room_nights, n.room_revenue
        order by adr_room_avg desc nulls last, n.space_type
        """,
        params + params,
    )
    return {
        "stay_month": stay_month if stay_month not in (None, "") else None,
        "room_types": [
            {
                "space_type": r["space_type"],
                "room_class": r["room_class"],
                "display_name": r["display_name"],
                "reservation_count": _i(r["reservation_count"]),
                "room_nights": _i(r["room_nights"]),
                "adr_room_avg": _money(r["adr_room_avg"]),
                "revenue_per_room_night": round(_f(r["room_revenue"]) / _i(r["room_nights"]), 2)
                if _i(r["room_nights"]) else 0.0,
            }
            for r in rows
        ],
    }


# The five tools the brief mandates by exact name (no run_sql escape hatch).
REQUIRED_TOOLS = [
    get_otb_summary,
    get_segment_mix,
    get_pickup_delta,
    get_as_of_otb,
    get_block_vs_transient_mix,
]

# All agent-facing tools (required five + supplementary ADR tool).
ALL_TOOLS = REQUIRED_TOOLS + [get_adr_by_room_type]
