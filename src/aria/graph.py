"""LangGraph Platform graph entrypoint.

This module exposes `graph` as a compiled LangGraph graph for use with
`langgraph serve` / LangGraph Platform (see langgraph.json).

The MCP client is initialised at import time. It intentionally stays open
for the lifetime of the process — LangGraph Platform manages restarts and
there is no shutdown hook needed.

For self-hosted cloud deployments, prefer serve.py (FastAPI + uvicorn),
which gives proper async lifespan management and SSE streaming.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import os

from dotenv import load_dotenv

from .agent import load_persona, make_mcp_client
from .config import get_write_tools, load_config
from .models import create_model

load_dotenv()


async def _build():
    config = load_config()
    role_name = os.getenv("ARIA_ROLE", "default")
    role = config.roles.get(role_name)
    if role is None:
        raise RuntimeError(
            f"Unknown role '{role_name}'. Set ARIA_ROLE to one of: "
            + ", ".join(config.roles)
        )

    server_names = role.servers or list(config.mcp_servers)
    servers = {n: config.mcp_servers[n] for n in server_names if n in config.mcp_servers}

    write_tools = get_write_tools(servers)
    system_prompt = load_persona(role.persona)

    client = make_mcp_client(servers)
    await client.__aenter__()  # intentionally not closed — process lifetime
    all_tools = await client.get_tools()
    tools = (
        [t for t in all_tools if t.name not in write_tools]
        if role.readonly
        else all_tools
    )

    model = create_model(os.getenv("ARIA_MODEL") or role.model)

    from langchain.agents import create_agent
    # LangGraph Platform injects its own checkpointer; we pass none here.
    return create_agent(model, tools, system_prompt=system_prompt)


def _run_async(coro):
    """Run a coroutine whether or not an event loop is already running."""
    try:
        asyncio.get_running_loop()
        # Inside a running event loop — run in a thread to avoid nesting.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        # No running loop — create one explicitly and close it cleanly.
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


graph = _run_async(_build())
