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
from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemPermission
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
SKILLS_DIR = ROOT / "skills"

# Skills middleware loads from the BACKEND, and a "source" is a directory whose
# children are skills (each child has a SKILL.md). We point at the skills/ dir;
# the 8 skill subdirs are discovered, CHALLENGE_SKILL.md (a loose file) is ignored.
# Backend-relative path (the agent runs on a FilesystemBackend rooted at the repo).
SKILL_SOURCES = ["skills"]

DEFAULT_MODEL = "anthropic:claude-opus-4-8"

# The segment subagent runs on a DIFFERENT model family so its calls draw from a
# separate rate-limit bucket. Anthropic meters Opus (4.6/4.7/4.8), Sonnet, and Haiku
# in independent ITPM pools, so delegating segment work to Haiku means it no longer
# consumes the main Opus 30k-ITPM Tier-1 budget — the fix for Tier-1 429s on heavy
# (subagent-delegating) questions when you can't tier up. Override via SUBAGENT_MODEL
# (e.g. anthropic:claude-sonnet-4-6 for more subagent quality, or the main model to
# disable the split). The segment tools do the arithmetic, so Haiku's lighter
# reasoning is low-risk here.
SUBAGENT_MODEL = os.environ.get("SUBAGENT_MODEL", "anthropic:claude-haiku-4-5")

# The filesystem backend exists only so the skills middleware can READ SKILL.md
# files. The agent has no business writing to the repo, so deny every write — this
# stops a weak model from "editing" a skill mid-answer (observed with gpt-4o-mini).
READ_ONLY_FS = [FilesystemPermission(operations=["write"], paths=["/**"], mode="deny")]


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
            # retry transient provider errors (429 / malformed bursts) so a
            # concurrent spike degrades gracefully instead of failing the turn
            max_retries=4,
            timeout=60,
        )
    if spec.startswith("groq:"):
        # Groq's OpenAI-compatible gateway — fast, free tier, separate quota.
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=spec.split(":", 1)[1],
            temperature=0,
            base_url="https://api.groq.com/openai/v1",
            api_key=os.environ.get("GROQ_API_KEY"),
            max_retries=4,
            timeout=60,
        )
    if spec.startswith("cerebras:"):
        # Cerebras OpenAI-compatible gateway — fast, free tier, separate quota.
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=spec.split(":", 1)[1],
            temperature=0,
            base_url="https://api.cerebras.ai/v1",
            api_key=os.environ.get("CEREBRAS_API_KEY"),
            max_retries=4,
            timeout=60,
        )
    if spec.startswith("anthropic:"):
        # Tier-1 limits are per-model-class: Opus 4.x = 50 RPM / 500k ITPM / 80k OTPM;
        # Haiku 4.5 (the subagent's separate bucket) = 50 RPM / 50k ITPM. (NB: the old
        # "Opus 30k ITPM" note here was the *Sonnet* number — Opus is 16x higher.)
        # A deep-agent question fires several tool rounds, each re-sending the whole
        # growing prefix (system + skills + tool defs + history). cache_control turns on
        # Anthropic prompt caching: that stable prefix is written once, then read on
        # every later round at ~0.1x cost AND — crucially — cache-read tokens do NOT
        # count toward ITPM on Opus / Haiku 4.x (no "†" in the rate-limit table), so the
        # burst stops stacking against the per-minute cap. {"type":"ephemeral"} as a
        # top-level kwarg auto-places the breakpoint on the last cacheable block (caches
        # tools+system+history as a prefix). max_retries rides out any residual 429.
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=spec.split(":", 1)[1],
            timeout=120,
            max_retries=8,
            model_kwargs={"cache_control": {"type": "ephemeral"}},
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
    "skills": SKILL_SOURCES,
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
    "skill_sources": SKILL_SOURCES,
    "uses_checkpointer": True,
    "uses_store": True,
}


def build_agent(model=None, checkpointer=None, store=None):
    """Build the compiled Deep Agent.

    model: a chat-model instance (e.g. a fake for tests) OR a 'provider:name' string;
           defaults to env MODEL or DEFAULT_MODEL. checkpointer/store default to
           in-memory implementations (swap for Postgres/Redis in deployment).
    """
    # Put the segment subagent on its own model family (separate rate-limit bucket).
    # Tests pass a model INSTANCE (a fake) — in that case let the subagent inherit it
    # so no API key is needed; only split on the real string/env path (production).
    subagent = dict(SEGMENT_SUBAGENT)
    if model is None or isinstance(model, str):
        subagent["model"] = resolve_model(SUBAGENT_MODEL)
    return create_deep_agent(
        model=resolve_model(model),
        tools=MAIN_TOOLS,
        system_prompt=MAIN_SYSTEM_PROMPT,
        subagents=[subagent],
        skills=SKILL_SOURCES,
        backend=FilesystemBackend(root_dir=str(ROOT), virtual_mode=True),
        permissions=READ_ONLY_FS,
        interrupt_on={HITL_TOOL: True},
        checkpointer=checkpointer or MemorySaver(),
        store=store or InMemoryStore(),
    )
