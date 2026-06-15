"""
Phase 3 agent tests (tests/AGENT_TEST_SCENARIOS.md), scenarios 1-7.

Structure / graph-introspection / fixture-trace only — no live LLM API calls.
The agent is built with a fake chat model so the LangGraph graph assembles with
no API key, then we assert on its wiring and on AGENT_CONFIG.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

from agent.build import AGENT_CONFIG, MAIN_SKILLS, SEGMENT_SKILLS, build_agent
from agent.tools import MAIN_TOOLS, SEGMENT_TOOLS

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ["get_otb_summary", "get_segment_mix", "get_pickup_delta",
            "get_as_of_otb", "get_block_vs_transient_mix"]


@pytest.fixture(scope="module")
def graph_nodes():
    agent = build_agent(model=GenericFakeChatModel(messages=iter([])))
    return set(agent.get_graph().nodes)


# --- Scenario 1: tool surface is fixed (5 required, no run_sql) ------------- #
def test_tool_surface_required_and_no_raw_sql():
    surface = AGENT_CONFIG["all_tool_names"]
    for name in REQUIRED:                       # all five required present by name
        assert name in surface, f"missing required tool {name}"
    assert "run_sql" not in surface and not any("sql" in n for n in surface)
    # supplementary tools are allowed (get_booking_pace, get_adr_by_room_type),
    # but there is no free-form SQL tool. Tools import without an HTTP server.
    assert all(hasattr(t, "name") for t in MAIN_TOOLS + SEGMENT_TOOLS)


# --- Scenario 2: get_as_of_otb is human-gated ------------------------------ #
def test_as_of_otb_is_human_gated(graph_nodes):
    assert AGENT_CONFIG["interrupt_on"] == {"get_as_of_otb": True}
    assert AGENT_CONFIG["hitl_tool"] == "get_as_of_otb"
    # the HITL middleware is actually wired into the compiled graph
    assert any("HumanInTheLoop" in n for n in graph_nodes), graph_nodes


# --- Scenario 3: segment work is isolated (pattern: subagent) --------------- #
def test_segment_work_isolated_via_subagent():
    # Pattern chosen: a dedicated `segment-analyst` SUBAGENT owns the mix tools.
    main = AGENT_CONFIG["main_tool_names"]
    seg = AGENT_CONFIG["segment_tool_names"]
    assert "segment-analyst" in AGENT_CONFIG["subagents"]
    assert "get_segment_mix" in seg and "get_block_vs_transient_mix" in seg
    # main agent deliberately lacks the mix tools -> segment questions must delegate
    assert "get_segment_mix" not in main and "get_block_vs_transient_mix" not in main


# --- Scenario 4: multi-tool decomposition (recorded trace fixture) --------- #
def test_multi_tool_decomposition_trace():
    trace = json.loads((ROOT / "tests/fixtures/composite_trace.json").read_text())
    tools_used = {c["tool"] for c in trace["tool_calls"]}
    assert len(tools_used) >= 2, "composite question must invoke >= 2 distinct tools"
    assert tools_used <= set(AGENT_CONFIG["all_tool_names"])


# --- Scenario 5: skills are on-demand SKILL.md, not a monolith -------------- #
def test_skills_loaded_on_demand(graph_nodes):
    assert any("Skills" in n for n in graph_nodes), graph_nodes
    paths = MAIN_SKILLS + SEGMENT_SKILLS
    assert paths, "no skill paths configured"
    for p in paths:                              # each configured skill path exists
        assert (Path(p) / "SKILL.md").is_file(), f"missing SKILL.md at {p}"


# --- Scenario 6: memory / filesystem used (not stateless) ------------------ #
def test_memory_configured():
    assert AGENT_CONFIG["uses_checkpointer"] and AGENT_CONFIG["uses_store"]
    agent = build_agent(model=GenericFakeChatModel(messages=iter([])))
    assert agent.checkpointer is not None        # multi-turn thread memory


# --- Scenario 7 (bonus): planning is wired --------------------------------- #
def test_planning_middleware_present(graph_nodes):
    assert any("Todo" in n for n in graph_nodes), graph_nodes
