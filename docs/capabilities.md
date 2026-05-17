# Capability MCP Servers

This guide covers setting up the MCP servers used in Aria's config examples.
Each capability is an independent MCP server — add only the ones you need.

---

## Web Search

Two options — pick one and set it as the `web-search` server in your roles.
Both are read-only (no `write_tools` needed).

### Option A — Brave Search

**Package:** `@brave/brave-search-mcp-server` (maintained by Brave)  
**Free tier:** 2,000 queries/month ([brave.com/search/api](https://brave.com/search/api/))  
**Good for:** Privacy-conscious deployments; enterprise use

```json
"web-search-brave": {
  "command": "npx",
  "args": ["-y", "@brave/brave-search-mcp-server"],
  "env": { "BRAVE_API_KEY": { "from": "env", "var": "BRAVE_API_KEY" } },
  "write_tools": []
}
```

1. Create a free account at [brave.com/search/api](https://brave.com/search/api/)
2. Generate an API key and add `BRAVE_API_KEY=BSA...` to your `.env`

### Option B — Tavily

**Package:** `tavily-mcp` (maintained by Tavily)  
**Free tier:** 1,000 searches/month ([tavily.com](https://tavily.com/))  
**Good for:** AI-agent workloads; widely used in the LangChain/LangGraph ecosystem

```json
"web-search-tavily": {
  "command": "npx",
  "args": ["-y", "tavily-mcp@latest"],
  "env": { "TAVILY_API_KEY": { "from": "env", "var": "TAVILY_API_KEY" } },
  "write_tools": []
}
```

1. Sign up at [app.tavily.com](https://app.tavily.com/)
2. Copy your API key and add `TAVILY_API_KEY=tvly-...` to your `.env`

> Both servers are installed on demand via `npx` — no separate `npm install` needed.
> The config examples include both blocks; reference whichever one you set up in
> your roles' `servers` array.

---

## Email — Gmail

### Option A — gongrzhe (self-hosted, 14 tools)

**Package:** `@gongrzhe/server-gmail-autoauth-mcp`  
**Stars:** 760+, actively maintained  
**Tools:** `send_email`, `create_draft`, `reply_to_email`, `forward_email`,
`delete_email`, `trash_email`, `modify_labels`, `search_emails`, `read_email`,
`list_labels`, and more (14 total)

This is the option wired into the config examples. It runs as a local subprocess
and handles the Gmail OAuth flow automatically on first run.

**Setup:**

**Step 1 — Create a GCP project** (skip if you already have one)

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Create a new project (e.g. `aria-agent`)

**Step 2 — Enable the Gmail API**

1. In your project: **APIs & Services → Library → Gmail API → Enable**

**Step 3 — Create OAuth 2.0 credentials**

1. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
2. Application type: **Desktop app**
3. Download the credentials JSON (e.g. `gmail-credentials.json`)

**Step 4 — Configure the consent screen**

1. **APIs & Services → OAuth consent screen**
2. User type: **External** (unless you have Google Workspace)
3. Fill in app name, support email, developer email
4. Add scope: `https://www.googleapis.com/auth/gmail.modify`
5. Add your email as a **test user**
6. Leave publishing status as **Testing** — no Google review needed for personal
   use or small deployments (up to 100 test users)

**Step 5 — Wire up Aria**

```
GMAIL_CREDENTIALS_PATH=/etc/aria/gmail-credentials.json
```

On first run the MCP server opens a browser for the OAuth consent flow and saves
a token file. Subsequent runs reuse the saved token.

For Docker, mount the credentials and persist the token directory:

```yaml
volumes:
  - ./gmail-credentials.json:/etc/aria/gmail-credentials.json
  - aria-gmail-token:/root/.gmail-mcp
```

> **Tool names vary by MCP server.** If you swap to a different Gmail MCP,
> update the `write_tools` array in your server block to match its actual tool names.

---

### Option B — Google's official hosted MCP

**Endpoint:** `https://gmailmcp.googleapis.com/mcp/v1`  
**Maintainer:** Google (official)  
**Tools:** 10 tools, focused on labels, drafts, and thread operations  
**Transport:** HTTP (not stdio)

This option is not yet wired into Aria's config examples because `McpServerConfig`
currently only models stdio servers (no `url` field). HTTP transport support is
planned. In the meantime, use Option A for full Gmail capabilities.

When HTTP transport support is added, the config block will look like:

```json
"gmail-google": {
  "transport": "streamable_http",
  "url": "https://gmailmcp.googleapis.com/mcp/v1",
  "env": {
    "GMAIL_CLIENT_ID": { "from": "env", "var": "GMAIL_CLIENT_ID" },
    "GMAIL_CLIENT_SECRET": { "from": "env", "var": "GMAIL_CLIENT_SECRET" }
  },
  "write_tools": ["create_draft", "create_label", "label_message", "label_thread"]
}
```

---

## Outlook / Microsoft 365

Not yet wired in. Planned alongside M365 OAuth identity (Phase 5). The pattern
will be the same: an MCP server block with an explicit `write_tools` list.

---

## Messaging — Twilio (SMS and WhatsApp)

**Package:** `@twilio-labs/mcp` (official Twilio Labs MCP)  
**Capabilities:** Send SMS, send WhatsApp messages (via Twilio's WhatsApp Business API),
manage Twilio resources  
**Write tools:** `create_message` (the primary mutating tool for sending SMS/WhatsApp)

**Setup:**

1. Sign up at [twilio.com](https://www.twilio.com/) — free trial includes credits
2. From the [Twilio Console](https://console.twilio.com/) → **Account Info**, copy:
   - **Account SID** (`ACxxxxxxxx...`)
   - **Auth Token**
3. For WhatsApp: enable the WhatsApp sandbox or apply for a WhatsApp Business number
   in the Twilio Console

```
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your-auth-token
```

Config block (already in the example configs):

```json
"messaging-twilio": {
  "command": "npx",
  "transport": "stdio",
  "args": ["-y", "@twilio-labs/mcp"],
  "env": {
    "TWILIO_ACCOUNT_SID": { "from": "env", "var": "TWILIO_ACCOUNT_SID" },
    "TWILIO_AUTH_TOKEN":  { "from": "env", "var": "TWILIO_AUTH_TOKEN" }
  },
  "write_tools": ["create_message"]
}
```

> **Verifying tool names:** `@twilio-labs/mcp` exposes tools derived from the Twilio
> REST API. Run `aria` once with the Twilio server connected and note what tools
> appear in the session. If the actual send tool has a different name, update
> `write_tools` in your config block to match, so readonly roles are filtered correctly.

---

## Remote MCP over HTTP/SSE

Instead of running an MCP server as a local subprocess inside the Aria container,
you can run it as a network service on the business's own LAN (secured via Tailscale)
and have cloud Aria connect to it over HTTP.

**Why this matters:**
- NAS credentials never leave the business's network — auth stays on-prem
- The Aria container needs no SMB credentials at all
- One MCP server instance can serve multiple Aria containers
- Works with any MCP server that supports streamable HTTP or SSE transport

**Architecture:**

```
Cloud (Docker)                    Business LAN (Tailscale)
┌──────────────────┐              ┌──────────────────────────┐
│  Aria container  │◄─ HTTP/SSE ──│  mcp-server-filesystem   │
│  (no NAS creds)  │   Tailscale  │  (direct NAS access,     │
└──────────────────┘              │   Kerberos/OS auth)       │
                                  └──────────────────────────┘
```

**Config block** (use your Tailscale hostname or IP):

```json
"nas-remote": {
  "transport": "streamable_http",
  "url": "https://nas.tail12345.ts.net:8080/mcp",
  "write_tools": ["write_file", "edit_file", "create_directory", "move_file", "delete_file"]
}
```

No `command`, `args`, or `env` — this is a network connection, not a subprocess.

**Running the remote MCP server on-prem:**

Any MCP server that supports HTTP transport can be used. For `mcp-server-filesystem`:

```bash
# On the domain-joined server (NAS already mounted at /mnt/nas)
npx @modelcontextprotocol/server-filesystem /mnt/nas --transport streamable-http --port 8080
```

Lock it down with Tailscale ACLs so only your cloud Aria node can reach port 8080.
Do not expose it to the public internet.

> HTTP/SSE transport is supported in Aria — use `"transport": "streamable_http"` or
> `"sse"` with a `"url"` field in your server block. The on-prem server setup is
> manual for now; systemd unit files are planned.

---

## Adding more MCP servers

Any MCP server follows the same pattern. Add a block to `aria.config.json`, add
it to the `servers` list of whichever roles should have access, and declare
`write_tools` explicitly so readonly role filtering works correctly.

For **stdio servers**: set `command`, `args`, and `env`. The subprocess only
receives the env vars you declare — credentials are isolated by default.

For **HTTP/SSE servers**: set `transport` to `"streamable_http"` or `"sse"` and
set `url`. No `command` or `env` needed — Aria connects over the network.
