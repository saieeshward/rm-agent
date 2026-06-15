#!/usr/bin/env python3
"""
Eval fact-checker (no LLM): verifies that the data-grounded numbers behind each
gold answer in evals/gold.yaml actually hold against the live tools. This is the
"build evaluations first" step — it proves the gold set is correct before we grade
the agent's live answers against the rubrics.

Run:  python evals/check_facts.py   (needs the loaded DB + venv)
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.revenue_tools import (  # noqa: E402
    get_adr_by_room_type, get_booking_pace, get_block_vs_transient_mix,
    get_otb_summary, get_segment_mix,
)

GOLD = Path(__file__).resolve().parent / "gold.yaml"


def _stly(month: str) -> str:
    y, m = month.split("-")
    return f"{int(y) - 1}-{m}"


# Each check returns (passed: bool, evidence: str).
def ota_share_lt_15(month):
    segs = get_segment_mix(month)["segments"]
    ota = next((s["share_of_revenue"] for s in segs if s["market_code"] == "OTA"), 0.0)
    stly = next((s["share_of_revenue"] for s in get_segment_mix(_stly(month))["segments"]
                 if s["market_code"] == "OTA"), 0.0)
    return ota < 0.15, f"OTA {ota:.1%} (STLY {stly:.1%}) < 15%"


def sep_mice_majority(month):
    segs = get_segment_mix(month)["segments"]
    mice = sum(s["share_of_revenue"] for s in segs if s["macro_group"] == "MICE")
    return mice > 0.50, f"MICE share_of_revenue {mice:.1%} > 50%"


def sep_block_concentrated(month):
    b = get_block_vs_transient_mix(month)
    named = [c for c in b["top_companies"] if c["company"] != "Transient"]
    named_share = sum(c["total_revenue"] for c in named) / max(
        get_otb_summary(month)["total_revenue"], 1)
    ok = b["block_share_of_revenue"] > 0.65 and named_share > 0.40
    return ok, f"block {b['block_share_of_revenue']:.1%} >65%, named-accounts {named_share:.1%} >40%"


def july_ahead_of_curve(month):
    cur = get_booking_pace(month)["share_booked_90plus"]
    stly = get_booking_pace(_stly(month))["share_booked_90plus"]
    return cur > stly, f"90+ booked {cur:.0%} vs STLY {stly:.0%} (ahead of curve)"


def ex_highest_adr(*_):
    rooms = get_adr_by_room_type()["room_types"]
    top = max(rooms, key=lambda r: r["adr_room_avg"])
    return top["space_type"] == "EX", f"highest ADR = {top['display_name']} £{top['adr_room_avg']}"


def june_cancel_small(month):
    inc = get_otb_summary(month, exclude_cancelled=False)
    exc = get_otb_summary(month)
    share = (inc["total_revenue"] - exc["total_revenue"]) / max(inc["total_revenue"], 1)
    return 0 < share < 0.10, f"cancelled share {share:.1%} (small)"


CHECKS = {fn.__name__: fn for fn in [
    ota_share_lt_15, sep_mice_majority, sep_block_concentrated,
    july_ahead_of_curve, ex_highest_adr, june_cancel_small,
]}


def main() -> int:
    gold = yaml.safe_load(GOLD.read_text())
    failures = 0
    for case in gold["cases"]:
        for fact in case.get("facts", []):
            fn = CHECKS[fact["check"]]
            try:
                passed, evidence = fn(*fact.get("args", []))
            except Exception as exc:  # pragma: no cover
                passed, evidence = False, f"error: {exc}"
            mark = "PASS" if passed else "FAIL"
            if not passed:
                failures += 1
            print(f"  [{mark}] {case['id']}: {fact['desc']} -> {evidence}")
        if not case.get("facts"):
            print(f"  [n/a ] {case['id']}: rubric-only (no data fact) — grade live")
    print(f"\n{'OK' if failures == 0 else 'FAILED'}: {failures} fact check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
