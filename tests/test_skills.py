"""
Phase 3 skill-pack tests (tests/SKILL_TEST_SCENARIOS.md), scenarios 1-7.

Pure filesystem / structure checks — no LLM calls. They validate the skill pack
itself: version pin, count, judgment depth, tool routing, distinct routing,
an adversarial guardrail, and concentration readiness.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"

REQUIRED_TOOL_NAMES = [
    "get_otb_summary", "get_segment_mix", "get_pickup_delta",
    "get_as_of_otb", "get_block_vs_transient_mix",
]
# numeric threshold like >35%, >= 0.4, < 25%, "below 120", "£40"
THRESHOLD_RE = re.compile(r"(>=|<=|>|<)\s*[£$]?\d|\d+\s*%|below\s+[£$]?\d|£\d", re.I)
ACTION_RE = re.compile(
    r"shift rate|hold bar|close ota|review block|push direct|raise rate|"
    r"drop restriction|require deposit|tighten|protect (?:transient|retail|availability)|"
    r"reprice|overbook|cut-?off|non-refundable",
    re.I,
)
GUARDRAIL_RE = re.compile(
    r"property_date|cancelled|provisional|row_count|stay rows.*reservation|"
    r"raw sql|effective macro",
    re.I,
)


def _parse(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---"), f"{path} missing YAML frontmatter"
    _, fm, body = text.split("---", 2)
    return yaml.safe_load(fm) or {}, body.strip()


def _skill_files() -> list[Path]:
    return sorted(SKILLS_DIR.rglob("SKILL.md"))


# --- Scenario 1: pack version pin ------------------------------------------ #
def test_challenge_skill_version_pin():
    f = SKILLS_DIR / "CHALLENGE_SKILL.md"
    assert f.is_file()
    fm, _ = _parse(f)
    assert "otel-rm-v2" in str(fm.get("description", ""))


# --- Scenario 2: minimum skill count + frontmatter ------------------------- #
def test_minimum_skill_count():
    files = _skill_files()
    assert len(files) >= 6, f"need >=6 SKILL.md, found {len(files)}"
    for f in files:
        fm, _ = _parse(f)
        assert fm.get("name"), f"{f} missing name"
        assert fm.get("description"), f"{f} missing description"


# --- Scenario 3: judgment skills (threshold + action, >=80 words) ---------- #
def test_judgment_skills():
    judgment = []
    for f in _skill_files():
        _, body = _parse(f)
        if THRESHOLD_RE.search(body) and ACTION_RE.search(body) and len(body.split()) >= 80:
            judgment.append(f.parent.name)
    assert len(judgment) >= 3, f"need >=3 judgment skills, found {len(judgment)}: {judgment}"


# --- Scenario 4: tool routing declared; no raw SQL ------------------------- #
def test_tool_routing_and_no_raw_sql():
    for f in _skill_files():
        fm, body = _parse(f)
        blob = (str(fm.get("description", "")) + " " + body)
        assert any(t in blob for t in REQUIRED_TOOL_NAMES), f"{f} names no required tool"
        assert "reservations_hackathon" not in blob, f"{f} references the raw table"
        assert not re.search(r"\bselect\b.+\bfrom\b", body, re.I), f"{f} embeds raw SQL"


# --- Scenario 5: distinct routing; covers pickup, mix, OTB ----------------- #
def test_distinct_routing_and_domain_coverage():
    names, descs = [], []
    tool_hits = {t: 0 for t in REQUIRED_TOOL_NAMES}
    for f in _skill_files():
        fm, body = _parse(f)
        names.append(fm["name"].strip())
        descs.append(re.sub(r"\s+", " ", str(fm["description"]).strip().lower()))
        for t in REQUIRED_TOOL_NAMES:
            if t in (str(fm.get("description", "")) + " " + body):
                tool_hits[t] += 1
    assert len(names) == len(set(names)), "duplicate skill names"
    assert len(descs) == len(set(descs)), "duplicate descriptions"
    assert tool_hits["get_pickup_delta"] >= 1   # pickup / pace
    assert tool_hits["get_segment_mix"] >= 1     # mix / segment
    assert tool_hits["get_otb_summary"] >= 1     # OTB summary


# --- Scenario 6: adversarial guardrail ------------------------------------- #
def test_adversarial_guardrail():
    guarded = [f.parent.name for f in _skill_files() if GUARDRAIL_RE.search(_parse(f)[1])]
    assert guarded, "no skill warns against a known trap"


# --- Scenario 7 (bonus): concentration readiness --------------------------- #
def test_concentration_readiness():
    hits = [
        f.parent.name for f in _skill_files()
        if re.search(r"share_of_revenue|block_share_of_revenue|top3_company_revenue_share",
                     _parse(f)[1])
    ]
    assert hits, "no skill encodes OTA/block concentration via share_of_revenue semantics"
