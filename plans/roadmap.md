# Aria — Product Roadmap

This document captures all architectural decisions and planned work across sessions.
Start here when resuming work in a new context. See `plans/architecture.md` for
the original design doc and `CLAUDE.md` for coding guidance.

---

## Architectural Decisions (Settled)

### Authentication & Credentials
- Credentials are resolved at startup by a **credential resolver** in `make_mcp_client`,
  not stored as plaintext in config. Resolution chain:
  `OS keychain (keyring) → env var → .env file → interactive prompt → error`
- `McpServerConfig.env` values can be **credential references** (objects) or plain strings:
  ```json
  "SMB_NAS_PASSWORD": { "from": "keychain", "service": "aria-nas", "key": "password" }
  "SMB_NAS_PASSWORD": { "from": "env", "var": "SMB_NAS_PASSWORD" }
  "SMB_NAS_PASSWORD": "literal-value"
  ```
- Kerberos/SSO is free: `make_mcp_client` already passes `os.environ` to subprocesses.
  If the MCP server's SMB library supports Kerberos, it picks up the ticket automatically.

### MCP Server Strategy
- Two supported paths for file access — both are valid, chosen per deployment:
  - **smb-mcp**: direct SMB connection, manages credentials itself. Right for Docker /
    cloud / machines that can't mount shares at the OS level.
  - **mcp-server-filesystem**: reads a local path. Right for domain-joined servers or
    machines with shares already OS-mounted. Zero credential management in Aria.
- **Remote MCP over HTTP/SSE**: a third path worth pursuing — a lightweight MCP server
  runs on the business's own network with direct NAS access, and Aria (in cloud) connects
  to it over HTTP/SSE via Tailscale. Keeps auth on the business's network entirely.

### Roles (formerly Profiles)
- "Profiles" renamed to **roles** — better reflects identity-driven assignment.
- In config: `"roles"` key replaces `"profiles"`.
- Role assignment: `--role` CLI flag for local/on-prem; OAuth group → role mapping for cloud.
- `identityMap` block in config maps OAuth group names to role names:
  ```json
  "identityMap": {
    "Finance Team":  "finance",
    "HR Department": "hr",
    "Domain Users":  "staff"
  }
  ```
- `readonly: true` remains a hard code-level guardrail (tool filtering before model sees them).

### Deployment Models
Two supported deployment targets:

**On-prem (domain-joined server)**
```
Domain-joined Linux/Windows server
  ├── NAS shares OS-mounted (Kerberos / machine account — no stored password)
  └── Aria → mcp-server-filesystem → /mnt/nas
Each user SSHs in, runs their own `aria` process → inherits OS identity → own permissions
```

**Cloud VM (Docker, always-on service)**
```
Cloud VM
  ├── Per-tenant Aria container (one per business)
  │     ├── Credentials in secrets manager / env
  │     └── Connects to business NAS via Tailscale
  └── Always-running LangGraph service (not a REPL)
        └── Users connect via web UI / API → per-session thread_id
```

Tailscale is the connectivity layer for cloud → on-prem NAS (native support on
Synology, QNAP, TrueNAS; zero firewall config for the business).

### Service Architecture (Cloud)
- Cloud Aria runs as a **persistent service** via `langgraph serve`, not a CLI REPL.
- Multiple concurrent users → each gets a `thread_id`; no new process per session.
- `MemorySaver` → persistent DB (SQLite for single-tenant, Postgres for multi-tenant).
- Sessions survive disconnects and service restarts.
- MCP clients are long-lived (per-tenant), not recreated per session.

### Multi-User Identity (Cloud)
- Auth via **OAuth 2.0** — Microsoft 365 or Google Workspace (businesses already have one).
- Identity → role mapping via `identityMap` in config.
- Revoking an M365/Google account automatically cuts Aria access.
- Per-session credential injection: role-mapped credentials injected at session start,
  not at service startup. Requires per-session MCP client instantiation (Phase 5).

---

## Phases

### Phase 1 — Core REPL ✅ Complete
Core CLI, provider-agnostic model factory, profile system, smb-mcp integration,
streaming, readonly tool filtering.

---

### Phase 2 — Credential Foundation ✅ Complete
*Scope: Aria codebase only. No deployment changes.*

- [x] Rename `profiles` → `roles` in `config.py`, `cli.py`, `aria.config.example.json`,
      `CLAUDE.md`, and `plans/`
- [x] Credential reference syntax: extend `McpServerConfig.env` to accept
      `dict` values (references) alongside plain strings
- [x] Credential resolver in `make_mcp_client`: expand references via `keyring` and
      env var lookup before spawning MCP subprocesses
- [x] Add `keyring` to `pyproject.toml` dependencies
- [x] Config examples: add `mcp-server-filesystem` alongside `smb-mcp` to
      `aria.config.example.json` showing both paths
- [x] Update `_WRITE_TOOLS` in `cli.py` as needed for `mcp-server-filesystem` tool names
- [x] `--role` flag replaces `--profile` in CLI (keep `--profile` as deprecated alias)

---

### Phase 3 — On-Prem Deployment ✅ Complete
*Scope: deployment docs + config examples. Minimal code.*

- [x] Deployment guide: domain-joined Linux server setup → `docs/deploy-linux.md`
      (realm/sssd AD join, CIFS mount, systemd service)
- [x] Deployment guide: domain-joined Windows Server setup → `docs/deploy-windows.md`
      (mapped drives, Windows service via NSSM or Task Scheduler)
- [x] Tailscale setup guide: NAS → server connectivity for non-domain cases → `docs/tailscale.md`
- [x] On-prem config example with finance/hr/staff roles → `aria.config.example.onprem.json`
- [x] Systemd unit file for running Aria as a service → `deploy/aria.service`

---

### Phase 4 — Cloud Foundation (Single Tenant) ✅ Complete
*Scope: Docker, LangGraph serve, persistent storage.*

- [x] `Dockerfile` for Aria container (Python 3.12-slim + Node.js for npx MCP servers)
- [x] `docker-compose.yml`: Aria service + Tailscale sidecar (shared network namespace)
- [x] `src/aria/serve.py`: FastAPI service with SSE streaming and SQLite persistence
      (replaces REPL for cloud mode; REPL kept for local/on-prem)
- [x] `src/aria/graph.py`: LangGraph Platform graph entrypoint (`langgraph.json`)
- [x] Replace `MemorySaver` with optional checkpointer in `make_agent`;
      serve mode uses `AsyncSqliteSaver` from `langgraph-checkpoint-sqlite`
- [x] `[serve]` optional extra in `pyproject.toml` (fastapi, uvicorn, sqlite checkpointer)
- [x] `WRITE_TOOLS` moved from `cli.py` to `config.py` — shared by CLI and serve
- [x] `aria.config.example.cloud.json`: Tailscale NAS + env-var credential references
- [x] `docs/secrets.md`: .env / Docker secrets / AWS+GCP+Azure / OS keychain options
- [x] `GET /health` endpoint in serve.py; Docker HEALTHCHECK in Dockerfile

---

### Phase 5 — Identity & Multi-User
*Scope: OAuth integration, role mapping, per-session credential injection.*

- [ ] OAuth 2.0 integration: Microsoft 365 (MSAL) and Google Workspace (google-auth)
- [ ] `identityMap` block in config schema and `config.py`
- [ ] Session auth middleware: validate OAuth token → resolve role at session start
- [ ] Per-session MCP client instantiation with role-mapped credentials
      (replaces single startup MCP client for cloud mode)
- [ ] Session management API: create, resume, list sessions per user
- [ ] Postgres checkpointer option for multi-tenant deployments
      (`langgraph-checkpoint-postgres`)

---

### Phase 6 — Web Interface
*Scope: user-facing UI via LangGraph Studio (no custom frontend).*

- [x] Evaluate UI options: LangGraph Studio chosen over agent-chat-ui (requires Platform
      API rewrite) and Chainlit (extra dependency). Studio is free, zero frontend code,
      and `graph.py` + `langgraph.json` are already configured.
- [x] Add `langgraph-cli[inmem]` to `[dev]` optional extras in `pyproject.toml`
- [x] Document `langgraph dev` in CLAUDE.md alongside CLI and HTTP service modes
- [ ] Test with real MCP servers connected (web search + Gmail)
- [ ] Evaluate Studio for non-technical users; revisit Chainlit if Studio UX is insufficient

---

### Phase 7 — Capabilities (MCP Servers)
*Scope: new MCP server integrations. Config + `_WRITE_TOOLS` updates only.*

- [x] Web search: `@modelcontextprotocol/server-brave-search` — added to all config
      examples; added to `analyst` and `default` roles; `write_tools: []` (read-only)
- [x] Email: `@gongrzhe/server-gmail-autoauth-mcp` — added to cloud + base config
      examples; write_tools declared per-server; `_BUILTIN_WRITE_TOOLS` expanded
- [x] `docs/capabilities.md`: setup guides for Brave Search and Gmail
- [x] Messaging: `@twilio-labs/mcp` chosen — SMS + WhatsApp Business via Twilio;
      added to all config examples; `write_tools: ["create_message"]`;
      setup guide in `docs/capabilities.md`
- [x] Remote MCP over HTTP/SSE: implemented — `McpServerConfig` gains `url` field;
      `make_mcp_client` branches on transport (stdio vs HTTP); example block in
      `aria.config.example.cloud.json`; setup guide in `docs/capabilities.md`

---

### Phase 8 — Advanced
- [ ] Multi-agent routing supervisor (LangGraph): cheap model for simple tasks,
      powerful model for complex — only if OpenRouter auto-routing is insufficient
- [ ] Knowledge base / long-term memory (SQLite or vector store) beyond conversation history
- [ ] Audit logging: what did Aria do, as which user, on which files

---

## Key Dependencies

| Concern | Library / Service |
|---------|------------------|
| Credential storage | `keyring` |
| SMB direct | `smb-mcp` + `smbprotocol` |
| SMB via OS mount | `mcp-server-filesystem` |
| Network connectivity | Tailscale |
| Service hosting | `langgraph serve` / LangGraph Platform |
| Session persistence | `langgraph-checkpoint-sqlite` / `-postgres` |
| M365 identity | `msal` |
| Google identity | `google-auth` + `google-auth-oauthlib` |

---

## Session Handoff Notes

When starting a new session to work on a phase:
1. Read `CLAUDE.md` — coding conventions and current architecture
2. Read this file — decisions and phase scope
3. Read `plans/architecture.md` — original design doc for deeper context
4. Run `git log --oneline -10` to see what's been done since last session
