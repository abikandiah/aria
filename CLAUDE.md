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
  config.py   — load aria.config.json; McpServerConfig, Role, AriaConfig dataclasses
  cli.py      — argparse REPL; --role / --model flags, streaming, readonly filtering
plans/
  architecture.md   — full design doc: model layer, MCP config format, roadmap
aria.config.example.json   — example config with smb-mcp, mcp-server-filesystem, and roles
.env.example               — all supported env vars
pyproject.toml
```

## Setup

```bash
pip install -e .
cp aria.config.example.json aria.config.json
# fill in MCP server env vars (e.g. SMB_NAS_HOST, ANTHROPIC_API_KEY)
```

## Running

```bash
aria                           # default role
aria --role browse             # read-only, cheaper model
aria --model openai:gpt-4o     # override model for this session
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

- **`agent.py`** is fully provider- and domain-agnostic. `make_agent(model, tools)` takes any `BaseChatModel` and any tool list. `MemorySaver` gives per-session conversation state.
- **`make_mcp_client`** merges `os.environ` with per-server env overrides so MCP subprocesses inherit the parent environment.
- **Streaming** uses `astream_events(version="v2")`. The CLI surfaces `on_tool_start` (tool name + inputs) and `on_chat_model_stream` (text tokens) events.
- **`init_chat_model`** lives in `langchain` (not `langchain_core`). The `langchain>=0.3.0` dependency is required for the direct-provider path.
- **`create_react_agent`** from `langgraph.prebuilt` is correct and not deprecated. Pylance may flag it as deprecated — this is a false positive (it confuses it with the old `langchain.agents` version).

## Phased Roadmap

Full roadmap with architectural decisions is in `plans/roadmap.md`. Read that first
when starting any new phase. Summary:

- **Phase 1** (complete): core REPL, provider-agnostic model factory, profile system, smb-mcp integration
- **Phase 2** (complete): credential foundation — `keyring` integration, credential reference syntax in config, renamed profiles → roles
- **Phase 3** (complete): on-prem deployment — domain-joined server guides, Tailscale, systemd service
- **Phase 4**: cloud foundation — Docker, `langgraph serve`, SQLite session persistence
- **Phase 5**: identity & multi-user — OAuth (M365/Google), role mapping, per-session credential injection
- **Phase 6**: web interface for non-technical users
- **Phase 7**: capability MCP servers — email, web search, messaging, remote MCP over HTTP/SSE
- **Phase 8**: multi-agent routing, long-term memory, audit logging
