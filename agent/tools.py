"""
LangChain tool wrappers around the pure revenue functions.

The functions in tools.revenue_tools stay plain (importable with no LangChain /
no server, for test_tools.py). Here we wrap them as StructuredTools so the Deep
Agent can call them — names and grain docstrings are preserved from the originals.

Tool split (see ARCHITECTURE.md):
  MAIN_TOOLS     — OTB, pickup, booking pace, ADR, as-of (HITL)
  SEGMENT_TOOLS  — segment mix, block vs transient  (the segment-analyst subagent)
Main has NO mix tools, so segment/concentration questions are forced to delegate.
"""

from __future__ import annotations

from langchain_core.tools import StructuredTool

from tools.revenue_tools import (
    get_adr_by_room_type,
    get_as_of_otb,
    get_block_vs_transient_mix,
    get_booking_pace,
    get_otb_comparison,
    get_otb_summary,
    get_pickup_delta,
    get_segment_mix,
)

# Pure functions -> StructuredTools (name + docstring schema inferred from each).
otb_summary_tool = StructuredTool.from_function(get_otb_summary)
pickup_delta_tool = StructuredTool.from_function(get_pickup_delta)
booking_pace_tool = StructuredTool.from_function(get_booking_pace)
adr_by_room_type_tool = StructuredTool.from_function(get_adr_by_room_type)
as_of_otb_tool = StructuredTool.from_function(get_as_of_otb)
otb_comparison_tool = StructuredTool.from_function(get_otb_comparison)
segment_mix_tool = StructuredTool.from_function(get_segment_mix)
block_vs_transient_tool = StructuredTool.from_function(get_block_vs_transient_mix)

MAIN_TOOLS = [
    otb_summary_tool,
    otb_comparison_tool,
    pickup_delta_tool,
    booking_pace_tool,
    adr_by_room_type_tool,
    as_of_otb_tool,
]
SEGMENT_TOOLS = [
    segment_mix_tool,
    block_vs_transient_tool,
]
ALL_TOOLS = MAIN_TOOLS + SEGMENT_TOOLS

# Name of the tool gated behind human approval (HITL).
HITL_TOOL = "get_as_of_otb"
