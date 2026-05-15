# Aria — Architecture Plan

## What It Is

Aria is a general-purpose AI task agent built on LangGraph. It connects to any
number of MCP servers (file shares, email, messaging, web search, etc.) and
exposes their tools to a configurable language model. The user interacts via an
interactive CLI; the agent works autonomously to complete multi-step tasks.

The MCP layer is the integration surface — adding a new capability means adding
an MCP server to config, not writing code.

---

## Current State (v0.1 — `smb-agent`)

- Single MCP connection: `smb-mcp` (SMB/CIFS file share tools)
- Hardcoded `ChatAnthropic` / `claude-sonnet-4-6`
- Basic streaming REPL
- No profiles, no multi-MCP support

---

## Target Architecture

```
┌─────────────────────────────────────────────────────┐
│  aria CLI                                           │
│  --profile <name>  --model <name>                   │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│  LangGraph ReAct Agent                              │
│  model: BaseChatModel (any provider)                │
│  memory: MemorySaver (per session)                  │
│  tools: unified pool from all connected MCP servers │
└────────────────┬────────────────────────────────────┘
                 │  MCP stdio / SSE
      ┌──────────┼──────────┬──────────┬──────────┐
      ▼          ▼          ▼          ▼          ▼
  smb-mcp    email-mcp   web-mcp   whatsapp   ...more
  (files)    (Gmail etc) (search)  (msgs)
```

---

## Model Layer

All model instantiation lives in `aria/models.py`. Two paths, auto-selected:

| Condition | Provider | Use case |
|-----------|----------|----------|
| `OPENAI_BASE_URL` set | `ChatOpenAI(base_url=...)` | OpenRouter, Ollama, LM Studio, vLLM, any OpenAI-compat endpoint |
| No base URL | `init_chat_model(name)` | Direct Anthropic, OpenAI, Google via their own SDKs |

```
# OpenRouter (one key, all models)
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=sk-or-...
model: anthropic/claude-sonnet-4-6

# Ollama (local, no key)
OPENAI_BASE_URL=http://localhost:11434/v1
model: llama3.1:8b

# Direct Anthropic
ANTHROPIC_API_KEY=sk-ant-...
model: claude-sonnet-4-6

# Direct OpenAI
OPENAI_API_KEY=sk-...
model: gpt-4o
```

The agent never sees a provider name — just a `BaseChatModel` instance.

---

## MCP Server Configuration

Aria reads MCP server definitions from `aria.config.json` (or `~/.aria/config.json`),
mirroring the format Claude Desktop already uses so configs are portable:

```json
{
  "mcpServers": {
    "files": {
      "command": "smb-mcp",
      "transport": "stdio",
      "env": {
        "SMB_NAS_HOST": "samba-nas",
        "SMB_NAS_USERNAME": "user",
        "SMB_NAS_PASSWORD": "pass"
      }
    },
    "search": {
      "command": "mcp-tavily",
      "transport": "stdio",
      "env": { "TAVILY_API_KEY": "..." }
    },
    "email": {
      "command": "mcp-gmail",
      "transport": "stdio",
      "env": { "GMAIL_CREDENTIALS_FILE": "~/.aria/gmail.json" }
    }
  }
}
```

Adding a new capability = one new block in this file.

---

## Agent Profiles

Profiles live in the same config file and pre-select model + MCP servers + system
prompt variant + tool permissions:

```json
{
  "profiles": {
    "browse": {
      "model": "claude-haiku-4-5",
      "servers": ["files"],
      "readonly": true,
      "description": "Fast, cheap — read and navigate shares only"
    },
    "analyst": {
      "model": "claude-sonnet-4-6",
      "servers": ["files", "search"],
      "readonly": true,
      "description": "Read files and search the web, produce reports"
    },
    "admin": {
      "model": "claude-sonnet-4-6",
      "servers": ["files", "email"],
      "readonly": false,
      "description": "Full access — write, delete, send"
    },
    "default": {
      "model": "claude-sonnet-4-6",
      "servers": ["files"],
      "readonly": false
    }
  }
}
```

`readonly: true` removes write/delete/send tools from the tool pool before the
agent sees them — hard guardrail, not just a prompt instruction.

---

## Package Structure

```
aria/                          ← repo root (rename from smb-agent)
  src/
    aria/
      __init__.py
      agent.py                 ← create_react_agent; accepts BaseChatModel + tools list
      models.py                ← create_model(name) factory
      config.py                ← load aria.config.json; resolve profiles + MCP defs
      cli.py                   ← argparse REPL; --model, --profile flags
  plans/
    architecture.md            ← this file
  .env.example
  aria.config.example.json     ← example MCP server + profile config
  pyproject.toml
```

---

## CLI Interface

```
aria [--profile PROFILE] [--model MODEL]

  --profile   Profile name from aria.config.json (default: "default")
  --model     Override the profile's model, e.g. openai:gpt-4o

Environment:
  ANTHROPIC_API_KEY / OPENAI_API_KEY / OPENAI_BASE_URL (for OpenRouter/Ollama)
  ARIA_CONFIG   Path to config file (default: ./aria.config.json)
```

---

## Phased Roadmap

### Phase 1 — Core (immediate)
- [ ] Rename package and repo to `aria`
- [ ] `models.py`: OpenRouter / Ollama / direct provider factory
- [ ] `config.py`: load `aria.config.json` (MCP servers + profiles)
- [ ] `agent.py`: accept `BaseChatModel` + tool list, remove Anthropic coupling
- [ ] `cli.py`: `--profile` / `--model` flags, readonly tool filtering
- [ ] `aria.config.example.json` with `smb-mcp` wired in

### Phase 2 — Email
- [ ] Evaluate: `mcp-gmail`, `mcp-outlook`, or custom email MCP
- [ ] Add `email` server to config example
- [ ] Add `analyst` + `admin` profiles to example

### Phase 3 — Web search + messaging
- [ ] Evaluate: Tavily MCP, Brave Search MCP, Exa MCP for web search
- [ ] Evaluate: Twilio MCP or WhatsApp Cloud API MCP for messaging
- [ ] Add to config example

### Phase 4 — Multi-agent routing (optional)
- [ ] LangGraph supervisor node that routes to a cheap model for simple
      tasks and a powerful model for complex ones
- [ ] Only needed if OpenRouter auto-routing is insufficient

### Phase 5 — Persistent memory
- [ ] Replace `MemorySaver` with a persistent store (SQLite or Redis)
      so context survives across sessions

---

## MCP Servers of Interest

| Capability | Candidates |
|------------|-----------|
| File shares | `smb-mcp` (this project) |
| Web search | Tavily MCP, Brave Search MCP, Exa MCP |
| Email | Gmail MCP, Outlook MCP |
| Messaging | Twilio MCP, WhatsApp Cloud API |
| Browser/scraping | Playwright MCP, Puppeteer MCP |
| Calendar | Google Calendar MCP |
| Databases | Postgres MCP, SQLite MCP |
| Code execution | E2B MCP |
