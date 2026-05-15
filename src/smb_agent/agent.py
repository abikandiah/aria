"""LangGraph ReAct agent wired to the smb-mcp MCP server."""
from __future__ import annotations

import os

from langchain_anthropic import ChatAnthropic
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

SYSTEM_PROMPT = """\
You are an SMB file share assistant. You help users browse, search, read, and \
manage files on corporate SMB/CIFS network shares.

Start every new conversation by calling smb_list_profiles to discover available \
connections, then smb_test_connection to confirm access before doing file operations.

For broad exploration tasks, list the share root first, then drill into relevant \
subdirectories. Prefer smb_search over recursive listing when the user is looking \
for a specific file. Use smb_grep to find files by content.

For complex or multi-step tasks, work through them methodically and summarise \
your findings clearly when done.\
"""


def make_mcp_client() -> MultiServerMCPClient:
    """Spawn smb-mcp as a stdio subprocess and expose its tools via MCP."""
    return MultiServerMCPClient({
        "smb": {
            "command": "smb-mcp",
            "transport": "stdio",
            "env": dict(os.environ),
        }
    })


async def make_agent(client: MultiServerMCPClient):
    """Load MCP tools and return a ready LangGraph ReAct agent."""
    tools = await client.get_tools()
    model = ChatAnthropic(model="claude-sonnet-4-6", max_tokens=8096)
    return create_react_agent(
        model,
        tools,
        prompt=SYSTEM_PROMPT,
        checkpointer=MemorySaver(),
    )
