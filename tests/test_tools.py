"""
Phase 2 tool property tests (tests/TOOL_TEST_SCENARIOS.md), scenarios 1-6, 8-12.

Run against the loaded Postgres with views applied. Structural properties, not
exact floats. Months are discovered from the DB (not hard-coded) so the suite
survives the dataset's daily anchor shift.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from tools.revenue_tools import (
    ALL_TOOLS,
    REQUIRED_TOOLS,
    get_adr_by_room_type,
    get_as_of_otb,
    get_block_vs_transient_mix,
    get_otb_summary,
    get_pickup_delta,
    get_segment_mix,
)

ROOT = Path(__file__).resolve().parents[1]


def _load_proof() -> dict:
    return json.loads((ROOT / "etl/LOAD_PROOF.json").read_text())


# --- month-discovery fixtures (robust to anchor drift) --------------------- #
@pytest.fixture(scope="module")
def busiest_month(loaded) -> str:
    with loaded.cursor() as cur:
        cur.execute(
            "select to_char(stay_date,'YYYY-MM') m from public.vw_stay_night_base "
            "group by 1 order by count(*) desc limit 1"
        )
        return cur.fetchone()[0]


@pytest.fixture(scope="module")
def cancelled_month(loaded) -> str | None:
    with loaded.cursor() as cur:
        cur.execute(
            "select to_char(stay_date,'YYYY-MM') m from public.reservations_hackathon "
            "where reservation_status='Cancelled' and financial_status='Posted' "
            "group by 1 order by count(*) desc limit 1"
        )
        row = cur.fetchone()
        return row[0] if row else None


@pytest.fixture(scope="module")
def provisional_month(loaded) -> str | None:
    with loaded.cursor() as cur:
        cur.execute(
            "select to_char(stay_date,'YYYY-MM') m from public.reservations_hackathon "
            "where financial_status='Provisional' and reservation_status<>'Cancelled' "
            "group by 1 order by count(*) desc limit 1"
        )
        row = cur.fetchone()
        return row[0] if row else None


@pytest.fixture(scope="module")
def ota_month(loaded) -> str | None:
    with loaded.cursor() as cur:
        cur.execute(
            "select to_char(stay_date,'YYYY-MM') m from public.vw_stay_night_base "
            "where market_code='OTA' group by 1 order by count(*) desc limit 1"
        )
        row = cur.fetchone()
        return row[0] if row else None


# --- Scenario 1: grain inequality ------------------------------------------ #
def test_grain_inequality(busiest_month):
    o = get_otb_summary(busiest_month)
    assert o["reservation_count"] < o["row_count"]
    assert o["room_nights"] >= o["reservation_count"]
    assert o["room_revenue"] <= o["total_revenue"]


# --- Scenario 2: cancellation filter changes counts ------------------------ #
def test_cancellation_filter_widens_counts(cancelled_month):
    if cancelled_month is None:
        pytest.skip("no Posted+Cancelled rows in dataset")
    excl = get_otb_summary(cancelled_month, exclude_cancelled=True)
    incl = get_otb_summary(cancelled_month, exclude_cancelled=False)
    assert incl["row_count"] > excl["row_count"]
    assert excl["reservation_count"] <= incl["reservation_count"]


# --- Scenario 3: segment shares sum to one --------------------------------- #
def test_segment_shares_sum_to_one(busiest_month):
    m = get_segment_mix(busiest_month)
    assert m["segments"], "expected segments in a populated month"
    assert abs(sum(s["share_of_room_nights"] for s in m["segments"]) - 1.0) < 1e-6
    assert abs(sum(s["share_of_revenue"] for s in m["segments"]) - 1.0) < 1e-6
    for s in m["segments"]:
        assert 0.0 <= s["share_of_room_nights"] <= 1.0
        assert 0.0 <= s["share_of_revenue"] <= 1.0


# --- Scenario 4: macro_group filter narrows the universe ------------------- #
def test_macro_group_filter_narrows(busiest_month):
    full = get_segment_mix(busiest_month)
    retail = get_segment_mix(busiest_month, macro_group="Retail")
    assert retail["denominator_room_nights"] <= full["denominator_room_nights"]
    for s in retail["segments"]:
        assert s["macro_group"] == "Retail"


# --- Scenario 5: pickup uses booking date, not stay date ------------------- #
def test_pickup_uses_booking_window(busiest_month):
    # create_datetime defines the booking window; future_stay_from filters stay_date.
    stay_from = f"{busiest_month}-01"
    wide = get_pickup_delta(3650, stay_from)
    narrow = get_pickup_delta(1, stay_from)
    assert narrow["new_reservations"] <= wide["new_reservations"]
    assert wide["future_stay_from"] == stay_from
    assert wide["window_start_utc"] < wide["window_end_utc"]


# --- Scenario 6: OTA concentration signal ---------------------------------- #
def test_ota_segment_present(ota_month):
    assert ota_month is not None, "OTA missing entirely — broken ETL"
    m = get_segment_mix(ota_month)
    ota = [s for s in m["segments"] if s["market_code"] == "OTA"]
    assert ota, f"OTA segment missing for {ota_month}"
    assert 0.0 < ota[0]["share_of_revenue"] < 1.0


# --- Scenario 8: provisional excluded from default OTB --------------------- #
def test_provisional_excluded_by_default(provisional_month, loaded):
    assert _load_proof()["aggregates"]["provisional_row_count"] > 0
    if provisional_month is None:
        pytest.skip("no provisional rows in a single month")
    default = get_otb_summary(provisional_month)  # Posted, non-cancelled
    with loaded.cursor() as cur:
        cur.execute(
            "select count(*) from public.reservations_hackathon "
            "where to_char(stay_date,'YYYY-MM')=%s and reservation_status<>'Cancelled'",
            (provisional_month,),
        )
        incl_provisional = cur.fetchone()[0]
    assert default["row_count"] < incl_provisional


# --- Scenario 9: as-of snapshot differs from current OTB ------------------- #
def test_as_of_differs_from_current(busiest_month):
    current = get_otb_summary(busiest_month)
    early = get_as_of_otb(busiest_month, "2026-01-01T00:00:00Z")
    # an early snapshot can only have fewer-or-equal bookings on the books
    assert early["room_nights"] <= current["room_nights"]
    assert early["as_of_utc"].startswith("2026-01-01")


# --- Scenario 10: property_date vs stay_date ------------------------------- #
def test_property_date_mismatch_matches_proof(loaded):
    expected = _load_proof()["aggregates"]["property_date_mismatch_count"]
    with loaded.cursor() as cur:
        cur.execute(
            "select count(*) from public.reservations_hackathon where property_date <> stay_date"
        )
        assert cur.fetchone()[0] == expected


# --- Scenario 11: block vs transient mix ----------------------------------- #
def test_block_transient_reconciles(busiest_month):
    b = get_block_vs_transient_mix(busiest_month)
    otb = get_otb_summary(busiest_month)
    assert b["block_room_nights"] + b["transient_room_nights"] == otb["room_nights"]
    assert 0.0 <= b["block_share_of_room_nights"] <= 1.0
    assert 0.0 <= b["block_share_of_revenue"] <= 1.0
    assert b["top3_company_revenue_share"] <= 1.0 + 1e-9
    assert len(b["top_companies"]) <= 3
    revs = [c["total_revenue"] for c in b["top_companies"]]
    assert revs == sorted(revs, reverse=True)


# --- Scenario 12: tool layer isolation ------------------------------------- #
def test_no_raw_sql_parameter():
    forbidden = {"sql", "query", "q", "statement", "stmt"}
    for fn in ALL_TOOLS:
        params = set(inspect.signature(fn).parameters)
        assert not (params & forbidden), f"{fn.__name__} exposes a raw-SQL-like param"


def test_required_tool_names_and_grain_docstrings():
    assert [f.__name__ for f in REQUIRED_TOOLS] == [
        "get_otb_summary", "get_segment_mix", "get_pickup_delta",
        "get_as_of_otb", "get_block_vs_transient_mix",
    ]
    # get_adr_by_room_type is a supplementary tool: in ALL_TOOLS, not REQUIRED_TOOLS.
    assert get_adr_by_room_type in ALL_TOOLS
    assert get_adr_by_room_type not in REQUIRED_TOOLS
    for fn in ALL_TOOLS:
        doc = (fn.__doc__ or "").lower()
        assert any(w in doc for w in ("grain", "room night", "reservation_count", "row_count")), \
            f"{fn.__name__} docstring must state grain"
