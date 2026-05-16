"""LangGraph ReAct agent — provider and tool agnostic."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import MemorySaver

from .config import McpServerConfig

_PERSONAS_DIR = Path(__file__).parent / "personas"

# Minimal set of env vars forwarded to every MCP subprocess. API keys and
# secrets are NOT inherited by default — each server receives only what its
# own config declares, plus these execution essentials.
_SUBPROCESS_ENV_PASSTHROUGH: frozenset[str] = frozenset({
    "PATH", "HOME", "USER", "TMPDIR", "TEMP", "TMP",
    "NODE_PATH", "NODE_OPTIONS", "NPM_CONFIG_PREFIX",
    "LANG", "LC_ALL", "LC_CTYPE",
})


def load_persona(path: str | None) -> str:
    """Return a system prompt string from a file path or built-in persona name.

    Resolution order:
    1. path is None  → built-in 'default' persona from src/aria/personas/.
    2. path exists as a file (absolute or CWD-relative) → read it directly.
    3. path is a bare name (no slashes) → look for it in src/aria/personas/.
    """
    if path is None:
        return (_PERSONAS_DIR / "default.md").read_text()

    p = Path(path)
    if p.exists():
        return p.read_text()

    # Treat as a built-in persona name; strip .md extension if present.
    builtin = _PERSONAS_DIR / f"{Path(path).stem}.md"
    if builtin.exists():
        return builtin.read_text()

    available = [f.stem for f in sorted(_PERSONAS_DIR.glob("*.md"))]
    raise FileNotFoundError(
        f"Persona not found: {path!r}. "
        f"Provide a file path or a built-in name: {available}"
    )


def _resolve_env(env: dict[str, str | dict]) -> dict[str, str]:
    """Resolve credential references in an MCP server env dict to plain strings.

    Supported reference forms:
      {"from": "keychain", "service": "aria-nas", "key": "password"}
      {"from": "env", "var": "SMB_NAS_PASSWORD"}
    Plain string values are passed through unchanged.
    """
    resolved: dict[str, str] = {}
    for k, v in env.items():
        if isinstance(v, str):
            resolved[k] = v
        elif isinstance(v, dict):
            source = v.get("from")
            if source == "keychain":
                import keyring  # deferred: only needed when keychain refs are used
                missing = [f for f in ("service", "key") if f not in v]
                if missing:
                    raise ValueError(
                        f"Keychain credential ref for '{k}' is missing fields: {missing}"
                    )
                service, key = v["service"], v["key"]
                secret = keyring.get_password(service, key)
                if secret is None:
                    raise ValueError(
                        f"Credential not found in keychain: service={service!r}, key={key!r}"
                    )
                resolved[k] = secret
            elif source == "env":
                if "var" not in v:
                    raise ValueError(
                        f"Env credential ref for '{k}' is missing the 'var' field"
                    )
                var = v["var"]
                val = os.environ.get(var)
                if val is None:
                    raise ValueError(
                        f"Credential env var not set: {var!r} (config key {k!r})"
                    )
                resolved[k] = val
            else:
                raise ValueError(f"Unknown credential source {source!r} for key {k!r}")
        else:
            raise ValueError(f"Invalid credential value type for key {k!r}: {type(v)}")
    return resolved


def make_mcp_client(servers: dict[str, McpServerConfig]) -> MultiServerMCPClient:
    """Build an MCP client from a dict of McpServerConfig objects.

    Each subprocess receives only the env vars it declares plus a minimal
    passthrough set. Full parent environment is not inherited to prevent
    credential leakage across server trust boundaries.
    """
    base_env = {k: v for k, v in os.environ.items() if k in _SUBPROCESS_ENV_PASSTHROUGH}
    return MultiServerMCPClient({
        name: {
            "command": cfg.command,
            "transport": cfg.transport,
            "args": cfg.args,
            "env": {**base_env, **_resolve_env(cfg.env)},
        }
        for name, cfg in servers.items()
    })


def make_agent(
    model: BaseChatModel,
    tools: list[BaseTool],
    checkpointer: Any = None,  # BaseCheckpointSaver | AsyncBaseCheckpointSaver
    system_prompt: str | None = None,
) -> Any:
    """Create a ReAct agent. Defaults to in-memory checkpointing when none is given."""
    return create_agent(
        model,
        tools,
        system_prompt=system_prompt if system_prompt is not None else load_persona(None),
        checkpointer=checkpointer if checkpointer is not None else MemorySaver(),
    )
