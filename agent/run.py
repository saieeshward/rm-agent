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
    config = {"configurable": {"thread_id": args.thread}, "recursion_limit": 12}
    today = datetime.date.today().isoformat()
    primer = (f"(Context: today is {today}; dataset anchor ~2026-06-14; "
              f"stay months are 'YYYY-MM', STLY = year minus one.)\n\n")
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
    print("\n=== ANSWER ===")
    print(getattr(final, "content", final))


if __name__ == "__main__":
    main()
