# Deep Agents — learning guide + build plan (our agent)

A teaching reference for how LangChain Deep Agents works and how we assemble ours.
Sources: LangChain Deep Agents docs (overview, skills, subagents, human-in-the-loop,
memory, middleware, backends) + LangChain tools.

---

## 1. The mental model: it's layers

```
Chat model (the brain)              anthropic:claude / google_genai:gemini / ...
  └─ Tool-calling agent loop        model ↔ tools, until a final answer (ReAct)
       └─ Middleware (the "deep")    planning · filesystem · subagents · skills · HITL · summarization
            └─ create_deep_agent()   composes all of the above into one LangGraph graph
```

A "deep agent" is just a **tool-calling agent with a stack of middleware**. Each
capability the brief asks for (planning, subagents, skills, memory, HITL) is one
middleware that `create_deep_agent()` wires in for you. You *configure* them; you
don't hand-roll them. A single `create_deep_agent()` with one SQL tool is a fail
precisely because it uses none of these layers.

---

## 2. The building blocks (each taught with our project)

### 2.1 Chat model
A string `provider:model` (e.g. `anthropic:claude-sonnet-4-6`,
`google_genai:gemini-2.5-flash`, `ollama:llama3.1`). Provider-agnostic — we read it
from a `MODEL` env var so we can swap free/paid without code changes.

### 2.2 Tools (`@tool`)
A tool is a Python function the model can call. In LangChain:
- **type hints are required** (they define the input schema the model sees),
- the **docstring becomes the tool description** (how the model decides to call it),
- return a `dict`/`str` (the model reads it back),
- `config` and `runtime` are reserved param names (injected, hidden from the model).

Our six tools live as **plain functions** in `tools/revenue_tools.py` (no LangChain
import — so `test_tools.py` imports them with no server). The agent layer wraps them
with `@tool`/`StructuredTool.from_function`, preserving the grain docstrings. This is
the brief's "own your correctness" principle: the SQL is in our tested code, the model
only picks which tool + args.

### 2.3 The agent loop
`messages → model → (tool calls) → tool results → model → … → final answer`. We don't
write the loop; `create_deep_agent` provides it. We invoke with
`agent.invoke({"messages":[{"role":"user","content":...}]}, config=...)`.

### 2.4 Planning (`write_todos` middleware, built-in)
Gives the agent a todo list to decompose multi-part questions ("what's driving July
*and* how did we book lately?") into ordered steps before calling tools. Free with
`create_deep_agent`; we nudge it in the system prompt.

### 2.5 Filesystem + backends
The agent gets `ls/read_file/write_file/edit_file/grep/glob` over a pluggable backend:
- **StateBackend** (default) — thread-scoped scratchpad; persists across turns *within
  a thread* via the checkpointer.
- **StoreBackend** — cross-thread durable store (Postgres/Redis/cloud `BaseStore`);
  needs a `namespace` factory for per-user isolation.
- **CompositeBackend** — routes path prefixes to different backends ("longer prefix
  wins"), e.g. `/memories/` → StoreBackend, everything else → StateBackend.
- (FilesystemBackend / LocalShellBackend exist but grant real disk/shell access — we
  don't need them and they're a security risk.)

### 2.6 Skills (progressive disclosure)
`SKILL.md` files passed via `skills=`. Only each skill's frontmatter
(`name`+`description`) is preloaded; the body is read on demand (a file-read tool
call — which is how the UI "sees" a skill load). Our `skills/` pack is already built
and SOTA-tuned. Routing lives in the descriptions; judgment in the bodies.

### 2.7 Subagents (`task` tool, built-in)
A subagent is a focused agent the main agent calls via `task(name, task)`. It has its
**own** system prompt, tools, and skills, and an **isolated context** (keeps the
supervisor's window clean). Spec is a dict: `{name, description, system_prompt, tools,
model?, skills?, interrupt_on?}`. We route segment/channel/group/concentration work to
a `segment-analyst` subagent — and by **not** giving the main agent the mix tools, those
questions are *forced* to delegate.

### 2.8 Memory
Two senses:
- **Multi-turn within a conversation** = a **checkpointer** (`MemorySaver` or a
  Postgres checkpointer) keyed by `thread_id`. Required for a non-stateless GM chat,
  and required for HITL resume.
- **Cross-session long-term** = a `StoreBackend` memory file (e.g.
  `/memories/gm-notes.md`) the agent reads/writes with `edit_file`. Bonus.

### 2.9 Human-in-the-loop (`interrupt_on`)
`interrupt_on={"get_as_of_otb": True}` pauses before that tool runs and returns an
interrupt the UI renders as approve/edit/reject. Resume with
`agent.invoke(Command(resume={"decisions":[{"type":"approve"}]}), config=...)`.
**Requires a checkpointer.** We gate the expensive point-in-time rebuild (`get_as_of_otb`).

### 2.10 Streaming (for the UI)
`agent.stream(...)` / `astream_events` emit tool calls, tool results, and subagent
activity live — which is exactly the "show your work" the deploy requires (tool +
skill calls visible). Agent Chat UI renders these (incl. interrupts) out of the box.

### 2.11 Middleware composition + custom middleware
`create_deep_agent` stacks the built-in middleware; we can add our own. We'll add one
**tool-error middleware** (`@wrap_tool_call`) so a bad arg (e.g. `get_otb_summary("July")`
→ `ValueError`) becomes a clean `ToolMessage` the model can self-correct from, instead
of crashing the run.

---

## 3. Our architecture (the wiring)

| Block | Choice |
|---|---|
| Model | `MODEL` env var (default documented; provider-agnostic) |
| Main tools | `get_otb_summary`, `get_pickup_delta`, `get_adr_by_room_type`, `get_as_of_otb` (HITL) |
| Subagent `segment-analyst` | tools: `get_segment_mix`, `get_block_vs_transient_mix`; skills: ota-dependency, segment-mix-shift, block-concentration |
| Skills (main) | router + monthly-otb-briefing, pickup-pace, rate-positioning, cancellation-risk, filter-guardrail |
| Planning | built-in `write_todos` |
| Memory | `MemorySaver` checkpointer (thread) + optional `/memories/` StoreBackend |
| HITL | `interrupt_on={"get_as_of_otb": True}` |
| Error handling | custom `@wrap_tool_call` → ValueError to ToolMessage |
| Persona | RM system prompt + answer contract + delegation rule + injected current date/anchor |

---

## 4. Build plan (file by file)

1. **`tools/db.py` → connection pool** (`psycopg_pool`) — the deployed server is
   concurrent; one shared connection is unsafe. (no key needed)
2. **`agent/tools.py`** — `@tool` wrappers around the six functions (StructuredTool,
   keep grain docstrings). (no key)
3. **`agent/prompts.py`** — system prompts (main persona + answer contract + delegation;
   segment-analyst prompt), current-date injected at invoke. (no key)
4. **`agent/build.py`** — `build_agent()` calling `create_deep_agent(...)` with model,
   tool split, subagent, skills, `interrupt_on`, checkpointer, backend, error
   middleware; expose an inspectable `AGENT_CONFIG` for tests. (no key to *build*)
5. **`tests/test_agent.py`** (≥4) — introspection only, no live LLM:
   - exactly the 5 required tools present by name, no `run_sql`
   - `interrupt_on` includes `get_as_of_otb`
   - segment work isolated (subagent configured with the mix tools)
   - skills wired (paths in config) + checkpointer/memory configured
   - multi-tool decomposition via a recorded trace fixture
6. **`agent/server.py`** — LangGraph/Agent Chat UI serve + `GET /health` + basic auth +
   streaming. (needs key only to actually answer)
7. **`ARCHITECTURE.md`** — distilled from this guide + the routing matrix.

**Key needed only at step 6 live-run.** Steps 1–5 + 7 are fully doable and testable
with no API key.
