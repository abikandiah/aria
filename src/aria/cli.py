"""Interactive REPL for Aria with streaming output."""
from __future__ import annotations

import argparse
import asyncio
import json

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from .agent import make_agent, make_mcp_client
from .config import load_config
from .models import create_model

_THREAD = {"configurable": {"thread_id": "session"}}

# Tool names that mutate state — stripped from the pool when readonly=True.
# Extend this set as new MCP servers are added.
_WRITE_TOOLS: set[str] = {
    "smb_write_file", "smb_delete", "smb_move", "smb_copy", "smb_mkdir",
    "send_email", "send_message", "send_whatsapp",
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="aria",
        description="Aria — AI task agent with MCP tool integrations",
    )
    p.add_argument(
        "--profile", default="default",
        help="Profile name from aria.config.json (default: 'default')",
    )
    p.add_argument(
        "--model",
        help=(
            "Model name, overrides the profile setting. "
            "Examples: claude-sonnet-4-6  openai:gpt-4o  llama3.1:8b"
        ),
    )
    p.add_argument(
        "--config",
        help="Path to aria.config.json (default: ./aria.config.json)",
    )
    return p.parse_args()


def _fmt_input(data: dict) -> str:
    return "  ".join(
        f"{k}={json.dumps(v)}"
        for k, v in data.items()
        if v not in ("", None, False, 0)
    )


async def _run(args: argparse.Namespace) -> None:
    config = load_config(args.config)

    profile = config.profiles.get(args.profile)
    if profile is None:
        available = ", ".join(config.profiles) or "(none)"
        raise SystemExit(f"Unknown profile '{args.profile}'. Available: {available}")

    model = create_model(args.model or profile.model)

    server_names = profile.servers or list(config.mcp_servers)
    servers = {n: config.mcp_servers[n] for n in server_names if n in config.mcp_servers}
    if not servers:
        raise SystemExit(
            f"No MCP servers available for profile '{args.profile}'. "
            "Check aria.config.json."
        )

    client = make_mcp_client(servers)

    async with client:
        all_tools = await client.get_tools()
        tools = (
            [t for t in all_tools if t.name not in _WRITE_TOOLS]
            if profile.readonly
            else all_tools
        )

        agent = await make_agent(model, tools)

        tag = f"[{args.profile}]" + (" [readonly]" if profile.readonly else "")
        print(f"Aria {tag}  (type 'exit' to quit)\n")

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
                    print(f"  [{name}  {tip}]".rstrip() if tip else f"  [{name}]", flush=True)
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
    load_dotenv()
    args = _parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
