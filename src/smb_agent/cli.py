"""Interactive REPL for the SMB agent with streaming output."""
from __future__ import annotations

import asyncio
import json

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from .agent import make_agent, make_mcp_client

_THREAD = {"configurable": {"thread_id": "session"}}


def _fmt_input(data: dict) -> str:
    """Compact key=value summary for tool call display, omitting empty values."""
    return "  ".join(
        f"{k}={json.dumps(v)}"
        for k, v in data.items()
        if v not in ("", None, False, 0)
    )


async def _run() -> None:
    load_dotenv()
    client = make_mcp_client()

    async with client:
        agent = await make_agent(client)
        print("SMB Assistant  (type 'exit' to quit)\n")

        while True:
            try:
                user_input = input("› ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                break

            print()
            in_text = False

            async for event in agent.astream_events(
                {"messages": [HumanMessage(content=user_input)]},
                config=_THREAD,
                version="v2",
            ):
                kind = event["event"]

                if kind == "on_tool_start":
                    tip = _fmt_input(event["data"].get("input") or {})
                    name = event["name"]
                    line = f"  [{name}  {tip}]" if tip else f"  [{name}]"
                    print(line, flush=True)
                    in_text = False

                elif kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    text = chunk.content if isinstance(chunk.content, str) else ""
                    if text:
                        if not in_text:
                            print()
                            in_text = True
                        print(text, end="", flush=True)

            print("\n")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
