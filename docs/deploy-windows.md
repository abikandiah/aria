# Aria — On-Prem Deployment: Domain-Joined Windows Server

This guide covers running Aria on a Windows Server that is joined to an Active Directory
domain, with NAS shares mapped as drives. Users log in (RDP or SSH) and run their own
`aria` process, inheriting their Windows identity and share permissions.

## Prerequisites

- Windows Server 2019 / 2022 (or Windows 10/11 for a single workstation)
- Server already domain-joined
- NAS shares accessible from the server
- Python 3.10+

---

## 1. Map NAS Shares

Map shares persistently for the service account (or per user via Group Policy):

```bat
net use F: \\nas\finance  /persistent:yes
net use H: \\nas\hr       /persistent:yes
net use S: \\nas\shared   /persistent:yes
```

Or via PowerShell:

```powershell
New-PSDrive -Name F -PSProvider FileSystem -Root \\nas\finance -Persist
```

For domain-joined machines, credentials come from Kerberos automatically — no
`/user:` or `/password:` flags needed.

> **Group Policy** — for multi-user servers, map drives in a GPO under
> *User Configuration → Preferences → Windows Settings → Drive Maps*.
> Each user gets their drives on login, scoped to their AD group membership.

---

## 2. Install Python and Aria

1. Download Python 3.10+ from [python.org](https://python.org) — check **Add to PATH**.
2. Install Aria:

```powershell
pip install aria   # once on PyPI
# or from source:
git clone https://github.com/your-org/aria C:\opt\aria
pip install -e C:\opt\aria
```

---

## 3. Configure Aria

```powershell
copy C:\opt\aria\aria.config.example.onprem.json C:\ProgramData\aria\aria.config.json
```

Edit `aria.config.json` to use Windows drive letters for server paths:

```json
{
  "mcpServers": {
    "finance-files": {
      "command": "npx",
      "transport": "stdio",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "F:\\"]
    },
    "shared-files": {
      "command": "npx",
      "transport": "stdio",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "S:\\"]
    }
  },
  "roles": {
    "finance": {
      "model": "claude-sonnet-4-6",
      "servers": ["finance-files"],
      "readonly": false
    },
    "staff": {
      "model": "claude-haiku-4-5-20251001",
      "servers": ["shared-files"],
      "readonly": true
    }
  }
}
```

Set environment variables (System → Advanced → Environment Variables, or via GPO):

```
ARIA_CONFIG   = C:\ProgramData\aria\aria.config.json
ANTHROPIC_API_KEY = sk-ant-...
```

---

## 4. User Access

Users log in and run Aria in PowerShell or Command Prompt:

```powershell
aria --role finance
aria --role staff
```

Their Windows identity controls share access — Aria reads the already-mapped drive.

---

## 5. Running as a Windows Service

For a shared endpoint (future Phase 4+ use), install as a service using
[NSSM](https://nssm.cc) (Non-Sucking Service Manager):

```bat
nssm install Aria "C:\Python310\Scripts\aria.exe"
nssm set Aria AppDirectory C:\ProgramData\aria
nssm set Aria AppEnvironmentExtra ARIA_CONFIG=C:\ProgramData\aria\aria.config.json
nssm set Aria ObjectName DOMAIN\aria-svc-account Password
nssm start Aria
```

Alternatively, use **Task Scheduler** with a trigger of "At system startup",
run as the service account, action `aria`.

> The service account must be domain-joined with access to the NAS shares it
> serves. Kerberos delegation may be required if the service accesses shares on
> behalf of end users.

---

## Troubleshooting

| Symptom | Likely cause |
|---------|-------------|
| `npx: command not found` | Node.js not installed or not on PATH |
| Drive not mapped | GPO not applied — run `gpupdate /force` |
| `Access denied` on share | AD group membership — check with `whoami /groups` |
| `ANTHROPIC_API_KEY not set` | Env var not propagated to the session; set in System env |
