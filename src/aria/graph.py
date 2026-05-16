"""LangGraph Platform graph entrypoint.

This module exposes `graph` as a compiled LangGraph graph for use with
`langgraph serve` / LangGraph Platform (see langgraph.json).

The MCP client is initialised at import time using asyncio.run().
It intentionally stays open for the lifetime of the process — LangGraph
Platform manages restarts and there is no shutdown hook needed.

For self-hosted cloud deployments, prefer serve.py (FastAPI + uvicorn),
which gives proper async lifespan management and SSE streaming.
"""
from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

from .agent import make_mcp_client, SYSTEM_PROMPT
from .config import WRITE_TOOLS, load_config
from .models import create_model

load_dotenv()


async def _build():
    config = load_config()
    role_name = os.getenv("ARIA_ROLE", "default")
    role = config.roles[role_name]
    server_names = role.servers or list(config.mcp_servers)
    servers = {n: config.mcp_servers[n] for n in server_names if n in config.mcp_servers}

    client = make_mcp_client(servers)
    await client.__aenter__()  # intentionally not closed — process lifetime
    all_tools = await client.get_tools()
    tools = (
        [t for t in all_tools if t.name not in WRITE_TOOLS]
        if role.readonly
        else all_tools
    )

    model = create_model(os.getenv("ARIA_MODEL") or role.model)

    from langgraph.prebuilt import create_react_agent
    # LangGraph Platform injects its own checkpointer; we pass none here.
    return create_react_agent(model, tools, prompt=SYSTEM_PROMPT)


graph = asyncio.run(_build())
