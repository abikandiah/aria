"""LangGraph ReAct agent — provider and tool agnostic."""
from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.base import BaseCheckpointSaver
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


def _resolve_env(env: dict[str, str | dict]) -> dict[str, str]:
    """Resolve credential references in an MCP server env dict to plain strings.

    Supported reference forms:
      {"from": "keychain", "service": "aria-nas", "key": "password"}
      {"from": "env", "var": "SMB_NAS_PASSWORD"}
    Plain string values are passed through unchanged.
    """
    resolved: dict[str, str] = {}
    for k, v in env.items():
        if isinstance(v, str):
            resolved[k] = v
        elif isinstance(v, dict):
            source = v.get("from")
            if source == "keychain":
                import keyring  # deferred: only needed when keychain refs are used
                service, key = v["service"], v["key"]
                secret = keyring.get_password(service, key)
                if secret is None:
                    raise ValueError(
                        f"Credential not found in keychain: service={service!r}, key={key!r}"
                    )
                resolved[k] = secret
            elif source == "env":
                var = v["var"]
                val = os.environ.get(var)
                if val is None:
                    raise ValueError(
                        f"Credential env var not set: {var!r} (config key {k!r})"
                    )
                resolved[k] = val
            else:
                raise ValueError(f"Unknown credential source {source!r} for key {k!r}")
        else:
            raise ValueError(f"Invalid credential value type for key {k!r}: {type(v)}")
    return resolved


def make_mcp_client(servers: dict[str, McpServerConfig]) -> MultiServerMCPClient:
    """Build an MCP client from a dict of McpServerConfig objects."""
    return MultiServerMCPClient({
        name: {
            "command": cfg.command,
            "transport": cfg.transport,
            "args": cfg.args,
            "env": {**os.environ, **_resolve_env(cfg.env)},
        }
        for name, cfg in servers.items()
    })


async def make_agent(
    model: BaseChatModel,
    tools: list[BaseTool],
    checkpointer: BaseCheckpointSaver | None = None,
):
    """Create a ReAct agent. Defaults to in-memory checkpointing when none is given."""
    return create_react_agent(
        model,
        tools,
        prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer if checkpointer is not None else MemorySaver(),
    )
