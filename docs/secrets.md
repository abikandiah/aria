# Aria — Secrets Management

Aria never stores credentials in its config file as plain text. The `env` block in
`aria.config.json` accepts credential references that are resolved at startup:

```json
"SMB_NAS_PASSWORD": { "from": "env",      "var": "SMB_NAS_PASSWORD" }
"SMB_NAS_PASSWORD": { "from": "keychain", "service": "aria-nas", "key": "password" }
```

How you inject those env vars depends on the deployment target.

---

## Option 1 — `.env` file (local / dev)

The simplest option. Create a `.env` next to `aria.config.json`:

```
ANTHROPIC_API_KEY=sk-ant-...
SMB_NAS_USERNAME=myuser
SMB_NAS_PASSWORD=s3cret
TS_AUTHKEY=tskey-auth-...
```

`load_dotenv()` in Aria's entrypoints picks this up automatically.
Pass it to Docker Compose with `env_file: .env` (already in `docker-compose.yml`).

> **Never commit `.env` to git.** The `.gitignore` already excludes it.

---

## Option 2 — Docker secrets (Swarm / Compose v3)

For production Docker deployments, inject secrets via Docker's secret mechanism:

```yaml
# docker-compose.yml (Swarm mode)
services:
  aria:
    secrets:
      - anthropic_key
      - smb_password
    environment:
      ANTHROPIC_API_KEY_FILE: /run/secrets/anthropic_key
      SMB_NAS_PASSWORD_FILE: /run/secrets/smb_password

secrets:
  anthropic_key:
    external: true
  smb_password:
    external: true
```

Note: Aria reads env vars, not `_FILE` vars. Use an entrypoint wrapper
(`entrypoint.sh`) to read the secret files and export them as env vars:

```bash
#!/bin/sh
export ANTHROPIC_API_KEY=$(cat /run/secrets/anthropic_key)
export SMB_NAS_PASSWORD=$(cat /run/secrets/smb_password)
exec "$@"
```

---

## Option 3 — Cloud secrets managers

Inject secrets as env vars at container startup via your cloud platform.

**AWS (ECS / Fargate)**
```json
{
  "secrets": [
    { "name": "ANTHROPIC_API_KEY", "valueFrom": "arn:aws:secretsmanager:...:anthropic-key" },
    { "name": "SMB_NAS_PASSWORD",   "valueFrom": "arn:aws:secretsmanager:...:smb-password" }
  ]
}
```

**GCP (Cloud Run)**
```yaml
env:
  - name: ANTHROPIC_API_KEY
    valueFrom:
      secretKeyRef:
        key: latest
        name: anthropic-key
```

**Azure (Container Apps)**
```yaml
secrets:
  - name: anthropic-key
    keyVaultUrl: https://myvault.vault.azure.net/secrets/anthropic-key
    identity: system
env:
  - name: ANTHROPIC_API_KEY
    secretRef: anthropic-key
```

In all cases, Aria sees these as plain env vars and the credential reference
`{"from": "env", "var": "..."}` resolves them transparently.

---

## Option 4 — OS keychain (on-prem only)

For domain-joined servers running the interactive CLI, store credentials in the
OS keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service):

```bash
python3 -c "import keyring; keyring.set_password('aria-nas', 'password', 'my-secret')"
```

Then reference it in config:
```json
"SMB_NAS_PASSWORD": { "from": "keychain", "service": "aria-nas", "key": "password" }
```

This never touches disk and survives password rotations — just update the keychain
entry, no config change needed.

---

## Secrets rotation

All approaches support rotation without redeployment:

| Approach | Rotation procedure |
|----------|--------------------|
| `.env` file | Edit file, restart Aria |
| Docker secrets | Update secret, redeploy service |
| AWS Secrets Manager | Update secret value; ECS picks it up on next task start |
| GCP / Azure | Update secret; restart revision |
| OS keychain | `keyring.set_password(...)`, restart Aria process |
