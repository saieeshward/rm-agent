"""
Assemble the Revenue Manager Deep Agent from the Deep Agents building blocks.

  Tools      — MAIN_TOOLS on the supervisor; SEGMENT_TOOLS on the subagent
  Subagent   — `segment-analyst` (forced delegation: main has no mix tools)
  Skills     — on-demand SKILL.md (split main vs subagent), progressive disclosure
  Planning   — built-in write_todos
  Memory     — MemorySaver checkpointer (multi-turn) + InMemoryStore (long-term)
  HITL       — interrupt_on get_as_of_otb (expensive point-in-time rebuild)
  Model      — env MODEL (provider-agnostic); pass a chat-model instance for keyless tests

`AGENT_CONFIG` mirrors the wiring so tests/test_agent.py can assert structure
without building the LLM or making API calls.
"""

from __future__ import annotations

import os
from pathlib import Path

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

try:  # load a gitignored .env so API keys never touch chat or git
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

from agent.prompts import MAIN_SYSTEM_PROMPT, SEGMENT_ANALYST_PROMPT
from agent.tools import HITL_TOOL, MAIN_TOOLS, SEGMENT_TOOLS
from tools.revenue_tools import REQUIRED_TOOLS

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"

MAIN_SKILLS = [str(SKILLS / s) for s in
               ("monthly-otb-briefing", "pickup-pace", "rate-positioning",
                "cancellation-risk", "filter-guardrail")]
SEGMENT_SKILLS = [str(SKILLS / s) for s in
                  ("segment-mix-shift", "ota-dependency", "block-concentration")]

DEFAULT_MODEL = "anthropic:claude-sonnet-4-6"


def resolve_model(model=None):
    """Resolve the MODEL spec into something create_deep_agent accepts.

    - a chat-model instance (e.g. a test fake) is passed through unchanged
    - 'ollama:<name>'      -> local ChatOllama (temperature=0 for termination)
    - 'openrouter:<name>'  -> ChatOpenAI on the OpenRouter gateway (OPENROUTER_API_KEY)
    - 'provider:name'      -> string for init_chat_model (anthropic / openai / google_genai)
    """
    if model is not None and not isinstance(model, str):
        return model  # already a chat-model instance
    spec = model or os.environ.get("MODEL", DEFAULT_MODEL)
    if spec.startswith("ollama:"):
        from langchain_ollama import ChatOllama
        return ChatOllama(model=spec.split(":", 1)[1], temperature=0)
    if spec.startswith("openrouter:"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=spec.split(":", 1)[1],
            temperature=0,
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY"),
        )
    return spec

SEGMENT_SUBAGENT = {
    "name": "segment-analyst",
    "description": (
        "Segment & concentration analyst. Delegate any question about segment/market "
        "mix, what is driving a month, OTA/channel reliance, group vs transient, or "
        "key-account concentration. Uses get_segment_mix and get_block_vs_transient_mix."
    ),
    "system_prompt": SEGMENT_ANALYST_PROMPT,
    "tools": SEGMENT_TOOLS,
    "skills": SEGMENT_SKILLS,
}

# Inspectable mirror of the wiring (for tests; no LLM needed).
AGENT_CONFIG = {
    "required_tool_names": [f.__name__ for f in REQUIRED_TOOLS],
    "main_tool_names": [t.name for t in MAIN_TOOLS],
    "segment_tool_names": [t.name for t in SEGMENT_TOOLS],
    "all_tool_names": [t.name for t in MAIN_TOOLS + SEGMENT_TOOLS],
    "interrupt_on": {HITL_TOOL: True},
    "hitl_tool": HITL_TOOL,
    "subagents": [SEGMENT_SUBAGENT["name"]],
    "main_skills": MAIN_SKILLS,
    "segment_skills": SEGMENT_SKILLS,
    "uses_checkpointer": True,
    "uses_store": True,
}


def build_agent(model=None, checkpointer=None, store=None):
    """Build the compiled Deep Agent.

    model: a chat-model instance (e.g. a fake for tests) OR a 'provider:name' string;
           defaults to env MODEL or DEFAULT_MODEL. checkpointer/store default to
           in-memory implementations (swap for Postgres/Redis in deployment).
    """
    return create_deep_agent(
        model=resolve_model(model),
        tools=MAIN_TOOLS,
        system_prompt=MAIN_SYSTEM_PROMPT,
        subagents=[SEGMENT_SUBAGENT],
        skills=MAIN_SKILLS,
        interrupt_on={HITL_TOOL: True},
        checkpointer=checkpointer or MemorySaver(),
        store=store or InMemoryStore(),
    )
