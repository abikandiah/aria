# Aria

A general-purpose AI task agent built on [LangGraph](https://github.com/langchain-ai/langgraph). Aria connects to MCP servers — file shares, email, web search, messaging, and more — and exposes their tools to a configurable language model. You interact via a streaming REPL; the agent works autonomously on multi-step tasks.

**Adding a capability = adding an MCP server entry in `aria.config.json`. No code changes required.**

---

## Quick start

```bash
pip install -e .
cp aria.config.example.json aria.config.json   # edit to taste
cp .env.example .env                           # add your API key(s)
aria
```

---

## Installation

Requires Python 3.10+.

```bash
pip install -e .            # CLI only
pip install -e ".[serve]"   # + HTTP service
pip install -e ".[dev]"     # + LangGraph Studio + tests
```

---

## Usage

### CLI

```bash
aria                          # default role
aria --role browse            # read-only, cheaper model
aria --role analyst           # research persona, no writes
aria --model openai:gpt-4o    # override model for this session
```

Each `aria` invocation gets an isolated conversation thread. Concurrent sessions do not share state.

### HTTP service

```bash
uvicorn aria.serve:app --reload          # development
docker compose up                        # production
```

Endpoints:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| POST | `/threads/{id}/invoke` | Synchronous invoke |
| GET | `/threads/{id}/stream` | SSE streaming |

Set `ARIA_ROLE` to select the role at startup.

### LangGraph Studio (web UI)

```bash
langgraph dev    # chat UI + graph visualiser at http://localhost:8123
```

---

## Configuration

`aria.config.json` uses the same MCP server format as Claude Desktop — configs are portable between them.

```json
{
  "mcpServers": {
    "local-files": {
      "command": "npx",
      "transport": "stdio",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/files"],
      "write_tools": ["write_file", "edit_file", "create_directory", "move_file"]
    },
    "web-search": {
      "command": "npx",
      "transport": "stdio",
      "args": ["-y", "tavily-mcp@latest"],
      "env": { "TAVILY_API_KEY": { "from": "env", "var": "TAVILY_API_KEY" } },
      "write_tools": []
    }
  },
  "roles": {
    "default": {
      "model": "claude-sonnet-4-6",
      "servers": ["local-files", "web-search"],
      "readonly": false,
      "persona": "default"
    },
    "browse": {
      "model": "claude-haiku-4-5-20251001",
      "servers": ["local-files"],
      "readonly": true,
      "persona": "browse"
    }
  }
}
```

See `aria.config.example.json` for a fuller example with SMB, Gmail, and Twilio. On-prem and cloud variants are in `aria.config.example.onprem.json` and `aria.config.example.cloud.json`.

### Credential references

Environment values in `env` blocks can be plain strings or references resolved at startup:

```json
{ "from": "env", "var": "MY_SECRET" }        // pulled from an env var
{ "from": "keychain", "service": "aria-nas", "key": "password" }  // system keyring
```

### Roles

Each role specifies a model, a set of MCP servers, a persona (system prompt), and whether writes are allowed. `readonly: true` removes write/delete/send tools from the pool *before the model sees them* — it is a code-level guardrail, not a prompt instruction.

### Personas

Persona files are Markdown system prompts in `src/aria/personas/`. Built-in options: `default`, `browse`, `analyst`. Set `persona` in a role to a built-in name or a path to a custom file.

---

## Model configuration

Model selection is in `src/aria/models.py`. Two paths are auto-detected:

| Condition | Provider path |
|-----------|--------------|
| `OPENAI_BASE_URL` set | `ChatOpenAI(base_url=...)` — OpenRouter, Ollama, LM Studio, vLLM |
| No base URL | `init_chat_model(name)` — direct Anthropic, OpenAI, Google |

```bash
# Direct Anthropic (default)
ANTHROPIC_API_KEY=sk-ant-...
ARIA_MODEL=claude-sonnet-4-6

# OpenRouter — one key, every model
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=sk-or-...
ARIA_MODEL=anthropic/claude-sonnet-4-6   # or openai/gpt-4o, meta-llama/..., etc.

# Ollama (local, no key required)
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
ARIA_MODEL=llama3.1:8b
```

The agent receives a `BaseChatModel` — it is unaware of the underlying provider.

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ARIA_MODEL` | `claude-sonnet-4-6` | Default model |
| `ARIA_ROLE` | `default` | Role for serve mode |
| `ARIA_CONFIG` | `./aria.config.json` | Config file path |
| `ARIA_DB_PATH` | `./aria.db` | SQLite session DB (serve mode) |
| `ARIA_MAX_TOKENS` | `8096` | Max output tokens per response |
| `ARIA_MAX_CONCURRENT_REQUESTS` | `10` | Concurrency cap (serve mode) |
| `ANTHROPIC_API_KEY` | — | Direct Anthropic access |
| `OPENAI_API_KEY` | — | OpenAI or OpenRouter access |
| `OPENAI_BASE_URL` | — | OpenAI-compatible endpoint |
| `BRAVE_API_KEY` | — | Brave Search MCP server |
| `TAVILY_API_KEY` | — | Tavily Search MCP server |
| `GMAIL_CREDENTIALS_PATH` | — | Gmail OAuth credentials JSON |
| `TWILIO_ACCOUNT_SID` | — | Twilio messaging |
| `TWILIO_AUTH_TOKEN` | — | Twilio messaging |
| `TS_AUTHKEY` | — | Tailscale auth key (Docker) |

See `.env.example` for the full list with comments.

---

## Docker

```bash
docker compose up
```

`docker-compose.yml` runs Aria alongside a Tailscale sidecar so the container can reach NAS shares on a private network without opening firewall ports. See `docs/tailscale.md` and `docs/deploy-linux.md`.

---

## Project layout

```
src/aria/
  agent.py       — LangGraph agent factory; persona loading; scoped MCP env
  models.py      — create_model() factory; two-path provider detection
  config.py      — load aria.config.json; credential resolution; write-tool filtering
  cli.py         — streaming REPL; --role / --model flags; UUID thread isolation
  serve.py       — FastAPI service; /health, /invoke, /stream endpoints
  graph.py       — LangGraph Platform entrypoint (langgraph.json)
  personas/      — Markdown system prompts (default, browse, analyst)
docs/            — deployment guides (Linux, Windows, Tailscale, secrets)
plans/           — architecture and roadmap documents
```

---

## Development

```bash
pip install -e ".[dev]"
pytest
langgraph dev    # interactive Studio
```

---

## License

[MIT](LICENSE)
