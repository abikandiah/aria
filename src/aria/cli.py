"""Interactive REPL for Aria with streaming output."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from .agent import load_persona, make_agent, make_mcp_client
from .config import get_write_tools, load_config
from .models import create_model


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="aria",
        description="Aria — AI task agent with MCP tool integrations",
    )
    p.add_argument(
        "--role", default=None,
        help="Role name from aria.config.json (default: 'default')",
    )
    p.add_argument(
        "--profile", default=None, dest="profile",
        help=argparse.SUPPRESS,  # deprecated alias for --role
    )
    p.add_argument(
        "--model",
        help=(
            "Model name, overrides the role setting. "
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
    if args.profile and not args.role:
        print("Warning: --profile is deprecated, use --role instead", file=sys.stderr)

    role_name = args.role or args.profile or "default"

    config = load_config(args.config)

    role = config.roles.get(role_name)
    if role is None:
        available = ", ".join(config.roles) or "(none)"
        raise SystemExit(f"Unknown role '{role_name}'. Available: {available}")

    model = create_model(args.model or role.model)

    server_names = role.servers or list(config.mcp_servers)
    servers = {}
    for n in server_names:
        if n in config.mcp_servers:
            servers[n] = config.mcp_servers[n]
        else:
            print(f"Warning: server '{n}' referenced in role '{role_name}' not found in config", file=sys.stderr)

    if not servers:
        raise SystemExit(
            f"No MCP servers available for role '{role_name}'. "
            "Check aria.config.json."
        )

    write_tools = get_write_tools(servers)
    system_prompt = load_persona(role.persona)
    client = make_mcp_client(servers)
    thread_config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async with client:
        all_tools = await client.get_tools()
        tools = (
            [t for t in all_tools if t.name not in write_tools]
            if role.readonly
            else all_tools
        )

        agent = make_agent(model, tools, system_prompt=system_prompt)

        tag = f"[{role_name}]" + (" [readonly]" if role.readonly else "")
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

            try:
                async for event in agent.astream_events(
                    {"messages": [HumanMessage(content=user_input)]},
                    config=thread_config,
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

            except Exception as exc:
                print(f"\n[Error: {exc}]", file=sys.stderr)

            print("\n")


def main() -> None:
    load_dotenv()
    args = _parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
