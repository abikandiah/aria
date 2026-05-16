# Aria — On-Prem Deployment: Domain-Joined Linux Server

This guide covers running Aria on a Linux server that is joined to an Active Directory
domain, with NAS shares mounted via Kerberos. Users SSH in and run their own `aria`
process; each inherits their OS identity and sees only the shares their AD account
can access.

## Prerequisites

- Ubuntu 22.04 / Debian 12 / RHEL 9 (or equivalent)
- Server already joined to the AD domain (see [AD Join](#1-ad-join) if not)
- NAS shares accessible from the server (direct LAN or Tailscale)
- Python 3.10+

---

## 1. AD Join

Install `realmd` and supporting packages:

```bash
# Ubuntu / Debian
sudo apt install -y realmd sssd sssd-tools adcli packagekit

# RHEL / Rocky
sudo dnf install -y realmd sssd adcli
```

Discover and join the domain (substitute your domain):

```bash
realm discover domain.local
sudo realm join -U Administrator domain.local
```

Verify:

```bash
id DOMAIN\\yourusername
realm list
```

> **Kerberos tickets** — users get a ticket at SSH login via `pam_sss`. Aria inherits
> this automatically; no stored credentials needed for share access.

---

## 2. Mount NAS Shares

Install CIFS utilities:

```bash
sudo apt install -y cifs-utils krb5-user  # Debian/Ubuntu
sudo dnf install -y cifs-utils krb5-workstation  # RHEL
```

Create mount points:

```bash
sudo mkdir -p /mnt/nas/shared /mnt/nas/finance /mnt/nas/hr
```

Add entries to `/etc/fstab` (Kerberos auth — no stored password):

```fstab
//nas.domain.local/shared  /mnt/nas/shared  cifs  sec=krb5,uid=0,gid=domain\domain\ users,file_mode=0660,dir_mode=0770,nofail,_netdev  0 0
//nas.domain.local/finance /mnt/nas/finance cifs  sec=krb5,uid=0,gid=domain\finance,file_mode=0660,dir_mode=0770,nofail,_netdev  0 0
//nas.domain.local/hr      /mnt/nas/hr      cifs  sec=krb5,uid=0,gid=domain\hr,file_mode=0660,dir_mode=0770,nofail,_netdev  0 0
```

Mount and verify:

```bash
sudo mount -a
ls /mnt/nas/shared
```

> If the NAS doesn't support Kerberos, use `sec=ntlmssp` with a service account
> credential file. See `credentials=` in `man mount.cifs`.

---

## 3. Install Aria

```bash
# System-wide Python 3.10+
sudo apt install -y python3 python3-pip python3-venv

# Install Aria (as root or into a shared venv)
pip install aria   # once published to PyPI
# or from source:
git clone https://github.com/your-org/aria /opt/aria
pip install -e /opt/aria
```

---

## 4. Configure Aria

Copy and edit the config:

```bash
cp /opt/aria/aria.config.example.onprem.json /etc/aria/aria.config.json
```

Set the config path in the environment (add to `/etc/environment` or user's `.bashrc`):

```bash
export ARIA_CONFIG=/etc/aria/aria.config.json
export ANTHROPIC_API_KEY=sk-ant-...
```

See `aria.config.example.onprem.json` for a full on-prem config with finance/hr/staff
roles pointing to the mounted paths above.

---

## 5. User Access

Each user SSHs in and runs Aria directly. Their Kerberos ticket grants access only
to the shares their AD groups allow:

```bash
ssh user@aria-server.domain.local
aria --role finance        # full access to /mnt/nas/finance
aria --role staff          # read-only access to /mnt/nas/shared
```

No credentials are stored in Aria's config — the OS identity is the auth layer.

---

## 6. Systemd Service (Optional)

For a shared service account (e.g. a future API endpoint), see `deploy/aria.service`.
Copy it to `/etc/systemd/system/`, adjust `User=` and `Environment=`, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aria
```

For the interactive-REPL on-prem model, per-user processes started at SSH login
are usually preferable; no service needed.

---

## Troubleshooting

| Symptom | Likely cause |
|---------|-------------|
| `id: DOMAIN\user: no such user` | sssd not running — `systemctl status sssd` |
| `mount: permission denied` | Kerberos ticket expired — `kinit` |
| `[Errno 13]` on file access | AD group membership doesn't include the share |
| `realm join` fails | DNS misconfigured — server must resolve the domain controller |
