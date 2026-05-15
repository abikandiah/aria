"""LangGraph ReAct agent — provider and tool agnostic."""
from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from .config import McpServerConfig

SYSTEM_PROMPT = """\
You are Aria, a general-purpose AI assistant. You have access to tools for \
managing files, searching the web, sending messages, and more — depending on \
what's connected in this session.

Work through tasks methodically. For file operations, start by listing \
available profiles and testing the connection. For broad exploration, list \
directories before reading files. Prefer targeted search over recursive listing.

For complex or multi-step tasks, plan your approach before executing, then \
summarise your findings clearly when done.\
"""


def make_mcp_client(servers: dict[str, McpServerConfig]) -> MultiServerMCPClient:
    """Build an MCP client from a dict of McpServerConfig objects."""
    return MultiServerMCPClient({
        name: {
            "command": cfg.command,
            "transport": cfg.transport,
            "args": cfg.args,
            "env": {**os.environ, **cfg.env},
        }
        for name, cfg in servers.items()
    })


async def make_agent(model: BaseChatModel, tools: list[BaseTool]):
    """Create a ReAct agent with the given model and tool list."""
    return create_react_agent(
        model,
        tools,
        prompt=SYSTEM_PROMPT,
        checkpointer=MemorySaver(),
    )
