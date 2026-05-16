# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Aria is a general-purpose AI task agent built on LangGraph. It connects to MCP servers (file shares, email, web search, messaging, etc.) and exposes their tools to a configurable language model. Users interact via an interactive REPL; the agent works autonomously on multi-step tasks.

Adding a new capability = adding an MCP server entry in `aria.config.json`. No code changes required.

## Layout

```
src/aria/
  agent.py    — create_react_agent wrapper; accepts BaseChatModel + tool list
  models.py   — create_model(name) factory; two-path provider detection
  config.py   — load aria.config.json; McpServerConfig, Role, AriaConfig dataclasses + WRITE_TOOLS
  cli.py      — argparse REPL; --role / --model flags, streaming, readonly filtering
  serve.py    — FastAPI service; /health + /threads/{id}/invoke + /threads/{id}/stream
  graph.py    — LangGraph Platform graph entrypoint (used by langgraph.json)
plans/
  architecture.md        — full design doc: model layer, MCP config format, roadmap
docs/
  deploy-linux.md        — domain-joined Linux server setup
  deploy-windows.md      — domain-joined Windows Server setup
  tailscale.md           — NAS connectivity via Tailscale
  secrets.md             — secrets management options
Dockerfile               — Python 3.12-slim + Node.js; runs uvicorn aria.serve:app
docker-compose.yml       — Aria + Tailscale sidecar
langgraph.json           — LangGraph Platform entrypoint
aria.config.example.json             — SMB + local-filesystem example
aria.config.example.onprem.json      — on-prem finance/hr/staff roles
aria.config.example.cloud.json       — cloud Tailscale + env-var credentials
.env.example             — all supported env vars
pyproject.toml
```

## Setup

```bash
pip install -e .
cp aria.config.example.json aria.config.json
# fill in MCP server env vars (e.g. SMB_NAS_HOST, ANTHROPIC_API_KEY)
```

## Running

**CLI (local / on-prem):**
```bash
aria                           # default role
aria --role browse             # read-only, cheaper model
aria --model openai:gpt-4o     # override model for this session
```

**HTTP service (cloud):**
```bash
pip install -e ".[serve]"
uvicorn aria.serve:app --reload        # development
docker compose up                      # production (requires aria.config.json + .env)
```

## Model Configuration

Model selection is in `models.py`. Two paths are auto-detected at startup:

| Condition | Path | Use case |
|-----------|------|----------|
| `OPENAI_BASE_URL` set | `ChatOpenAI(base_url=...)` | OpenRouter, Ollama, LM Studio, vLLM |
| No base URL | `init_chat_model(name)` | Direct Anthropic, OpenAI, Google |

Key env vars:
```
ARIA_MODEL          default model name (fallback: claude-sonnet-4-6)
OPENAI_BASE_URL     e.g. https://openrouter.ai/api/v1 or http://localhost:11434/v1
OPENAI_API_KEY      required for OpenRouter; set to "ollama" for local Ollama
ANTHROPIC_API_KEY   required for direct Anthropic
```

The agent receives a `BaseChatModel` — it knows nothing about the underlying provider.

## Config File Format

`aria.config.json` mirrors Claude Desktop's MCP server format (configs are portable):

```json
{
  "mcpServers": {
    "smb-files": {
      "command": "smb-mcp",
      "transport": "stdio",
      "env": {
        "SMB_NAS_HOST": "samba-nas",
        "SMB_NAS_USERNAME": "myuser",
        "SMB_NAS_PASSWORD": { "from": "keychain", "service": "aria-nas", "key": "password" }
      }
    },
    "local-files": {
      "command": "npx",
      "transport": "stdio",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/mnt/nas"]
    }
  },
  "roles": {
    "default": { "model": "claude-sonnet-4-6", "servers": ["smb-files"], "readonly": false },
    "browse":  { "model": "claude-haiku-4-5-20251001", "servers": ["smb-files"], "readonly": true },
    "local":   { "model": "claude-sonnet-4-6", "servers": ["local-files"], "readonly": false }
  }
}
```

**Credential references** — `env` values can be plain strings or reference objects:
- `{ "from": "keychain", "service": "aria-nas", "key": "password" }` — resolved via `keyring`
- `{ "from": "env", "var": "SMB_NAS_PASSWORD" }` — resolved from an env var at startup

`readonly: true` removes write/delete/send tools from the pool **before the model sees them** — a code-level guardrail, not a prompt instruction. The write tool names are listed in `_WRITE_TOOLS` in `cli.py`; extend that set when adding new MCP servers with mutating tools.

## Architecture Notes

- **`agent.py`** is fully provider- and domain-agnostic. `make_agent(model, tools, checkpointer=None)` takes any `BaseChatModel` and any tool list. Defaults to `MemorySaver`; pass `AsyncSqliteSaver` for persistent sessions.
- **`make_mcp_client`** merges `os.environ` with per-server env overrides so MCP subprocesses inherit the parent environment. Credential references are resolved via `_resolve_env()`.
- **`WRITE_TOOLS`** is defined in `config.py` — extend it there when adding new MCP servers with mutating tools. Both CLI and serve mode import it from there.
- **Streaming** uses `astream_events(version="v2")`. CLI surfaces `on_tool_start` and `on_chat_model_stream`; serve mode forwards these as SSE events.
- **`init_chat_model`** lives in `langchain` (not `langchain_core`). The `langchain>=0.3.0` dependency is required for the direct-provider path.
- **`create_react_agent`** from `langgraph.prebuilt` is the correct import for LangGraph v1.x. LangGraph emits a deprecation warning that it will move in v2.0 — this is expected and harmless until we upgrade to v2.
- **Serve mode** (`serve.py`) uses FastAPI with async lifespan to hold the MCP client and SQLite checkpointer open for the life of the process. `ARIA_ROLE` and `ARIA_DB_PATH` env vars control runtime behaviour.
- **`graph.py`** exposes the agent for LangGraph Platform (`langgraph.json`). It uses `asyncio.run()` at import time — only works in a fresh event loop (standard for `langgraph serve` startup).

## Phased Roadmap

Full roadmap with architectural decisions is in `plans/roadmap.md`. Read that first
when starting any new phase. Summary:

- **Phase 1** (complete): core REPL, provider-agnostic model factory, profile system, smb-mcp integration
- **Phase 2** (complete): credential foundation — `keyring` integration, credential reference syntax in config, renamed profiles → roles
- **Phase 3** (complete): on-prem deployment — domain-joined server guides, Tailscale, systemd service
- **Phase 4** (complete): cloud foundation — Docker, FastAPI serve mode, SQLite session persistence
- **Phase 5**: identity & multi-user — OAuth (M365/Google), role mapping, per-session credential injection
- **Phase 6**: web interface for non-technical users
- **Phase 7**: capability MCP servers — email, web search, messaging, remote MCP over HTTP/SSE
- **Phase 8**: multi-agent routing, long-term memory, audit logging
