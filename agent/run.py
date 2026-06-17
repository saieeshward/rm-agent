"""
CLI runner for the Revenue Manager Deep Agent.

  python -m agent.run "what's driving July?"
  python -m agent.run "as of 2026-05-01 how did August look?" --approve

Uses whatever MODEL is set (e.g. MODEL=ollama:llama3.1:8b for a local, key-free
run). Streams tool/skill calls, handles the get_as_of_otb approval interrupt, and
prints the final answer. The same graph is what gets served in deployment.
"""

from __future__ import annotations

import argparse
import datetime

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from agent.build import build_agent


def _print_chunk(chunk: dict) -> None:
    for node, update in chunk.items():
        for msg in (update or {}).get("messages", []) if isinstance(update, dict) else []:
            if isinstance(msg, AIMessage):
                for tc in (msg.tool_calls or []):
                    name = tc["name"]
                    label = "skill" if name in ("read_file", "ls") else "tool"
                    print(f"  → {label}: {name}({tc.get('args', {})})")
            elif isinstance(msg, ToolMessage):
                preview = str(msg.content)[:160].replace("\n", " ")
                print(f"    ↳ {msg.name}: {preview}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("question")
    ap.add_argument("--thread", default="cli")
    ap.add_argument("--approve", action="store_true",
                    help="auto-approve the get_as_of_otb HITL interrupt (default: reject)")
    args = ap.parse_args()

    agent = build_agent()
    # Each agent turn traverses several middleware nodes, so a legit multi-tool
    # answer needs well over the LangGraph default; 50 allows that yet still
    # halts a runaway (e.g. a small model re-calling the same tool dozens of times).
    config = {"configurable": {"thread_id": args.thread}, "recursion_limit": 50}
    # Anchor "today" to the loaded dataset (read from the DB so it never goes stale in
    # code); fall back to the real clock if the manifest can't be read.
    anchor = datetime.date.today().isoformat()
    try:
        from tools.db import query_one
        man = query_one("select scraped_at::date::text as anchor "
                        "from public.load_manifest order by load_id desc limit 1") or {}
        anchor = man.get("anchor") or anchor
    except Exception:
        pass
    y, m, _d = (int(p) for p in anchor.split("-"))
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    primer = (f"(Context: treat today as {anchor} — the dataset anchor; if a month "
              f"isn't specified use the upcoming month {ny:04d}-{nm:02d}. Stay months "
              f"are 'YYYY-MM', STLY = year minus one.)\n\n")
    payload: object = {"messages": [{"role": "user", "content": primer + args.question}]}

    from langgraph.errors import GraphRecursionError
    while True:
        try:
            for chunk in agent.stream(payload, config=config, stream_mode="updates"):
                _print_chunk(chunk)
        except GraphRecursionError:
            print("\n[stopped] hit step limit — the model looped instead of "
                  "answering (typical of small local models; use a stronger model).")
            return
        state = agent.get_state(config)
        if not state.next:           # no pending interrupt -> done
            break
        decision = {"type": "approve"} if args.approve else {
            "type": "reject", "message": "as-of rebuild not approved in CLI"}
        print(f"  [HITL] get_as_of_otb interrupt -> {decision['type']}")
        payload = Command(resume={"decisions": [decision]})

    final = agent.get_state(config).values["messages"][-1]
    content = getattr(final, "content", final)
    if isinstance(content, list):  # provider content blocks (e.g. Gemini) -> text
        content = "\n".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        ) or str(content)
    print("\n=== ANSWER ===")
    print(content)


if __name__ == "__main__":
    main()
