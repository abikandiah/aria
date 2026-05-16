# Aria — NAS Connectivity via Tailscale

Tailscale is the recommended connectivity layer when Aria cannot reach the NAS directly
(cloud VM, remote laptop, or a server outside the domain). It creates a peer-to-peer
WireGuard mesh — the NAS appears on a stable private IP without any firewall changes.

Synology, QNAP, and TrueNAS all have native Tailscale packages, so no Linux VM is
needed on the NAS side.

---

## Architecture

```
Aria host (cloud VM / laptop)
  └── Tailscale → 100.x.y.z (NAS Tailscale IP)
        └── smb-mcp → SMB share on NAS
        OR
        └── CIFS mount → mcp-server-filesystem → /mnt/nas
```

Both paths work. Use **smb-mcp** if you can't mount the share at the OS level
(e.g. Docker, cloud VM). Use **mcp-server-filesystem** if you can mount it
(e.g. domain-joined Linux server with Tailscale for WAN reachability).

---

## 1. Install Tailscale on the NAS

### Synology DSM 7+

1. Open **Package Center** → search for **Tailscale** → Install.
2. Open Tailscale → **Log in** → authenticate with your Tailscale account.
3. Note the NAS's Tailscale IP (shown in the Tailscale admin panel, e.g. `100.64.0.5`).

### QNAP QTS / QuTS hero

1. Open **App Center** → search for **Tailscale** → Install.
2. Launch Tailscale → connect and authenticate.

### TrueNAS SCALE

1. **Apps** → search **Tailscale** → Install.
2. Provide your auth key (generate one at `login.tailscale.com/admin/settings/keys`).

### TrueNAS CORE / FreeNAS

Run Tailscale in a jail:

```bash
iocage create -n tailscale -r 13.2-RELEASE boot=on
iocage console tailscale
pkg install tailscale
sysrc tailscaled_enable=YES
service tailscaled start
tailscale up --authkey=tskey-auth-...
```

---

## 2. Install Tailscale on the Aria Host

```bash
# Linux
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# macOS
brew install --cask tailscale
open -a Tailscale   # authenticate via menu bar

# Windows
winget install Tailscale.Tailscale
# authenticate via the system tray icon
```

After authentication both devices should appear green in the Tailscale admin console.

---

## 3a. Option A — smb-mcp over Tailscale

Use the NAS's Tailscale IP directly in your Aria config. No OS-level mount needed.

```json
{
  "mcpServers": {
    "nas-files": {
      "command": "smb-mcp",
      "transport": "stdio",
      "env": {
        "SMB_NAS_HOST": "100.64.0.5",
        "SMB_NAS_USERNAME": "myuser",
        "SMB_NAS_PASSWORD": { "from": "keychain", "service": "aria-nas", "key": "password" }
      }
    }
  },
  "roles": {
    "default": { "model": "claude-sonnet-4-6", "servers": ["nas-files"], "readonly": false }
  }
}
```

Replace `100.64.0.5` with your NAS's Tailscale IP (or MagicDNS hostname, e.g.
`nas.tail12345.ts.net`).

> **MagicDNS** — enable it in the Tailscale admin console to get stable hostnames
> instead of IPs. The hostname format is `<device-name>.<tailnet>.ts.net`.

---

## 3b. Option B — CIFS mount over Tailscale + mcp-server-filesystem

Mount the share at the OS level using the Tailscale IP, then point
`mcp-server-filesystem` at the mount point.

```bash
# Linux — add to /etc/fstab
//100.64.0.5/shared  /mnt/nas  cifs  credentials=/etc/aria/nas.creds,uid=1000,gid=1000,nofail,_netdev  0 0
```

`/etc/aria/nas.creds`:
```
username=myuser
password=secret
domain=WORKGROUP
```

```bash
sudo mount -a
```

Then in `aria.config.json`:

```json
{
  "mcpServers": {
    "nas-files": {
      "command": "npx",
      "transport": "stdio",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/mnt/nas"]
    }
  }
}
```

---

## 4. Verify

```bash
# Confirm Tailscale connectivity
tailscale ping 100.64.0.5

# Confirm share is reachable (Option A)
smbclient -L //100.64.0.5 -U myuser

# Confirm mount (Option B)
ls /mnt/nas

# Run Aria
aria --role default
```

---

## Access Control

Tailscale **ACLs** (in the admin console) let you restrict which devices can reach
the NAS. Example: only allow the Aria host to reach the NAS on SMB port 445:

```json
{
  "acls": [
    { "action": "accept", "src": ["tag:aria-host"], "dst": ["tag:nas:445"] }
  ],
  "tagOwners": {
    "tag:aria-host": ["autogroup:admin"],
    "tag:nas":       ["autogroup:admin"]
  }
}
```

Apply tags to devices in the Tailscale admin console or with
`tailscale up --advertise-tags=tag:aria-host`.
