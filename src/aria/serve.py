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
import re
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from .agent import load_persona, make_agent, make_mcp_client
from .config import get_write_tools, load_config
from .models import create_model

_THREAD_ID_RE = re.compile(r"^[\w\-]{1,128}$")


def _check_thread_id(thread_id: str) -> None:
    if not _THREAD_ID_RE.match(thread_id):
        raise HTTPException(
            400,
            "thread_id must be 1–128 characters: alphanumeric, underscore, or hyphen",
        )


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
    missing = [n for n in server_names if n not in config.mcp_servers]
    if missing:
        import warnings
        warnings.warn(f"Servers referenced in role '{role_name}' not found: {missing}")
    if not servers:
        raise RuntimeError(
            f"No MCP servers configured for role '{role_name}'. Check aria.config.json."
        )

    db_path = os.getenv("ARIA_DB_PATH", "aria.db")

    system_prompt = load_persona(role.persona)
    write_tools = get_write_tools(servers)

    client = make_mcp_client(servers)
    async with client:
        all_tools = await client.get_tools()
        tools = (
            [t for t in all_tools if t.name not in write_tools]
            if role.readonly
            else all_tools
        )

        async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
            app.state.agent = make_agent(model, tools, checkpointer=checkpointer, system_prompt=system_prompt)
            app.state.ready = True
            try:
                yield
            finally:
                app.state.ready = False
                app.state.agent = None


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
    message: str = Field(..., min_length=1, max_length=100_000)


def _thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


@app.post("/threads/{thread_id}/invoke")
async def invoke(thread_id: str, req: ChatRequest, request: Request):
    """Single-turn invoke — waits for the full response before returning."""
    _check_thread_id(thread_id)
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(503, "Agent not ready")

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=req.message)]},
        config=_thread_config(thread_id),
    )
    messages = result.get("messages", [])
    if not messages:
        raise HTTPException(500, "Agent returned no messages")
    return {"thread_id": thread_id, "response": messages[-1].content}


async def _event_stream(agent, thread_id: str, message: str) -> AsyncIterator[str]:
    try:
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
    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
    finally:
        yield "data: [DONE]\n\n"


@app.post("/threads/{thread_id}/stream")
async def stream(thread_id: str, req: ChatRequest, request: Request):
    """Streaming chat via Server-Sent Events.

    Each SSE event carries a JSON payload:
      {"type": "text",       "content": "..."}  — model token(s)
      {"type": "tool_start", "name": "..."}      — tool invocation started
      {"type": "tool_end",   "name": "..."}      — tool invocation finished
      {"type": "error",      "message": "..."}   — agent or MCP error
    Followed by the sentinel:  data: [DONE]
    """
    _check_thread_id(thread_id)
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(503, "Agent not ready")

    return StreamingResponse(
        _event_stream(agent, thread_id, req.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
