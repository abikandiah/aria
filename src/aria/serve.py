"""HTTP service for cloud / API mode.

Run locally:   uvicorn aria.serve:app --reload
Docker:        CMD ["uvicorn", "aria.serve:app", "--host", "0.0.0.0", "--port", "8000"]

Environment variables (on top of the standard Aria ones):
  ARIA_ROLE      role name to activate at startup (default: "default")
  ARIA_DB_PATH   path to the SQLite session database (default: ./aria.db)
"""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from .agent import make_agent, make_mcp_client
from .config import WRITE_TOOLS, load_config
from .models import create_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()

    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # deferred: serve extra

    config = load_config()
    role_name = os.getenv("ARIA_ROLE", "default")
    role = config.roles.get(role_name)
    if role is None:
        raise RuntimeError(
            f"Unknown role '{role_name}'. Set ARIA_ROLE to one of: "
            + ", ".join(config.roles)
        )

    model = create_model(os.getenv("ARIA_MODEL") or role.model)
    server_names = role.servers or list(config.mcp_servers)
    servers = {n: config.mcp_servers[n] for n in server_names if n in config.mcp_servers}
    if not servers:
        raise RuntimeError(
            f"No MCP servers configured for role '{role_name}'. Check aria.config.json."
        )

    db_path = os.getenv("ARIA_DB_PATH", "aria.db")

    client = make_mcp_client(servers)
    async with client:
        all_tools = await client.get_tools()
        tools = (
            [t for t in all_tools if t.name not in WRITE_TOOLS]
            if role.readonly
            else all_tools
        )

        async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
            app.state.agent = await make_agent(model, tools, checkpointer=checkpointer)
            app.state.ready = True
            yield

    app.state.ready = False


app = FastAPI(title="Aria", version="0.1.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health(request: Request):
    ready = getattr(request.app.state, "ready", False)
    if not ready:
        raise HTTPException(503, "Agent not ready")
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str


def _thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


@app.post("/threads/{thread_id}/invoke")
async def invoke(thread_id: str, req: ChatRequest, request: Request):
    """Single-turn invoke — waits for the full response before returning."""
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(503, "Agent not ready")

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=req.message)]},
        config=_thread_config(thread_id),
    )
    last = result["messages"][-1]
    return {"thread_id": thread_id, "response": last.content}


async def _event_stream(agent, thread_id: str, message: str) -> AsyncIterator[str]:
    async for event in agent.astream_events(
        {"messages": [HumanMessage(content=message)]},
        config=_thread_config(thread_id),
        version="v2",
    ):
        kind = event["event"]
        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            text = chunk.content if isinstance(chunk.content, str) else ""
            if text:
                yield f"data: {json.dumps({'type': 'text', 'content': text})}\n\n"
        elif kind == "on_tool_start":
            payload = {"type": "tool_start", "name": event["name"]}
            yield f"data: {json.dumps(payload)}\n\n"
        elif kind == "on_tool_end":
            payload = {"type": "tool_end", "name": event["name"]}
            yield f"data: {json.dumps(payload)}\n\n"
    yield "data: [DONE]\n\n"


@app.post("/threads/{thread_id}/stream")
async def stream(thread_id: str, req: ChatRequest, request: Request):
    """Streaming chat via Server-Sent Events.

    Each SSE event carries a JSON payload:
      {"type": "text",       "content": "..."}  — model token(s)
      {"type": "tool_start", "name": "..."}      — tool invocation started
      {"type": "tool_end",   "name": "..."}      — tool invocation finished
    Followed by the sentinel:  data: [DONE]
    """
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(503, "Agent not ready")

    return StreamingResponse(
        _event_stream(agent, thread_id, req.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
