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

### Phase 2 — Credential Foundation
*Scope: Aria codebase only. No deployment changes.*

- [ ] Rename `profiles` → `roles` in `config.py`, `cli.py`, `aria.config.example.json`,
      `CLAUDE.md`, and `plans/`
- [ ] Credential reference syntax: extend `McpServerConfig.env` to accept
      `dict` values (references) alongside plain strings
- [ ] Credential resolver in `make_mcp_client`: expand references via `keyring` and
      env var lookup before spawning MCP subprocesses
- [ ] Add `keyring` to `pyproject.toml` dependencies
- [ ] Config examples: add `mcp-server-filesystem` alongside `smb-mcp` to
      `aria.config.example.json` showing both paths
- [ ] Update `_WRITE_TOOLS` in `cli.py` as needed for `mcp-server-filesystem` tool names
- [ ] `--role` flag replaces `--profile` in CLI (keep `--profile` as deprecated alias)

---

### Phase 3 — On-Prem Deployment
*Scope: deployment docs + config examples. Minimal code.*

- [ ] Deployment guide: domain-joined Linux server setup
      (realm/sssd AD join, CIFS mount, systemd service)
- [ ] Deployment guide: domain-joined Windows Server setup
      (mapped drives, Windows service via NSSM or Task Scheduler)
- [ ] Tailscale setup guide: NAS → server connectivity for non-domain cases
- [ ] `aria.config.example.json`: on-prem role examples
      (finance/hr/staff with mcp-server-filesystem paths)
- [ ] Systemd unit file for running Aria as a service

---

### Phase 4 — Cloud Foundation (Single Tenant)
*Scope: Docker, LangGraph serve, persistent storage.*

- [ ] `Dockerfile` for Aria container
- [ ] `docker-compose.yml`: Aria service + Tailscale sidecar
- [ ] Switch from CLI REPL to `langgraph serve` for cloud mode
      (keep CLI for local/on-prem — both modes supported)
- [ ] Replace `MemorySaver` with SQLite-backed checkpointer
      (`langgraph-checkpoint-sqlite`) for session persistence
- [ ] `aria.config.example.cloud.json`: cloud role + credential reference examples
- [ ] Secrets management: document env file vs Docker secrets vs secrets manager
- [ ] Health check endpoint

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
*Scope: user-facing UI for non-technical employees.*

- [ ] Evaluate LangGraph's built-in UI vs lightweight custom frontend
- [ ] WebSocket / SSE streaming to browser
- [ ] Session history view (past conversations)
- [ ] Role-aware UI (show/hide capabilities based on role)
- [ ] Mobile-friendly

---

### Phase 7 — Capabilities (MCP Servers)
*Scope: new MCP server integrations. Config + `_WRITE_TOOLS` updates only.*

- [ ] Email: evaluate `mcp-gmail` / `mcp-outlook` — pick one, add to config example
- [ ] Web search: evaluate Tavily / Brave / Exa MCPs
- [ ] Messaging: evaluate Twilio / WhatsApp Cloud API MCPs
- [ ] Remote MCP over HTTP/SSE: evaluate running `smb-mcp` or `mcp-server-filesystem`
      as a network-accessible service on the business's LAN (Tailscale-secured),
      connected to by cloud Aria over HTTP transport

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
