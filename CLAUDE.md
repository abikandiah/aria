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
  config.py   — load aria.config.json; McpServerConfig, Profile, AriaConfig dataclasses
  cli.py      — argparse REPL; --profile / --model flags, streaming, readonly filtering
plans/
  architecture.md   — full design doc: model layer, MCP config format, roadmap
aria.config.example.json   — example config with smb-mcp and default/browse profiles
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
aria                           # default profile
aria --profile browse          # read-only, cheaper model
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
    "files": {
      "command": "smb-mcp",
      "transport": "stdio",
      "env": { "SMB_NAS_HOST": "...", "SMB_NAS_USERNAME": "...", "SMB_NAS_PASSWORD": "..." }
    }
  },
  "profiles": {
    "default": { "model": "claude-sonnet-4-6", "servers": ["files"], "readonly": false },
    "browse":  { "model": "claude-haiku-4-5-20251001", "servers": ["files"], "readonly": true }
  }
}
```

`readonly: true` removes write/delete/send tools from the pool **before the model sees them** — a code-level guardrail, not a prompt instruction. The write tool names are listed in `_WRITE_TOOLS` in `cli.py`; extend that set when adding new MCP servers with mutating tools.

## Architecture Notes

- **`agent.py`** is fully provider- and domain-agnostic. `make_agent(model, tools)` takes any `BaseChatModel` and any tool list. `MemorySaver` gives per-session conversation state.
- **`make_mcp_client`** merges `os.environ` with per-server env overrides so MCP subprocesses inherit the parent environment.
- **Streaming** uses `astream_events(version="v2")`. The CLI surfaces `on_tool_start` (tool name + inputs) and `on_chat_model_stream` (text tokens) events.
- **`init_chat_model`** lives in `langchain` (not `langchain_core`). The `langchain>=0.3.0` dependency is required for the direct-provider path.
- **`create_react_agent`** from `langgraph.prebuilt` is correct and not deprecated. Pylance may flag it as deprecated — this is a false positive (it confuses it with the old `langchain.agents` version).

## Phased Roadmap

- **Phase 1** (complete): core REPL, provider-agnostic model factory, profile system, smb-mcp integration
- **Phase 2**: email MCP (evaluate mcp-gmail / mcp-outlook)
- **Phase 3**: web search (Tavily/Brave/Exa) + messaging (Twilio/WhatsApp)
- **Phase 4**: multi-agent routing supervisor (optional — OpenRouter may handle this)
- **Phase 5**: persistent memory (SQLite/Redis replacing MemorySaver)
