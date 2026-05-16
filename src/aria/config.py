"""Load Aria configuration from aria.config.json.

Config file format mirrors Claude Desktop's MCP server format so configs
are portable between tools. Roles layer model and permission settings
on top of the server list.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class McpServerConfig:
    command: str
    transport: str = "stdio"
    args: list[str] = field(default_factory=list)
    env: dict[str, str | dict] = field(default_factory=dict)


@dataclass
class Role:
    name: str
    model: str | None = None
    servers: list[str] = field(default_factory=list)
    readonly: bool = False
    description: str = ""


@dataclass
class AriaConfig:
    mcp_servers: dict[str, McpServerConfig]
    roles: dict[str, Role]


# Tool names that mutate state; stripped from the pool when readonly=True.
# Extend this set when adding new MCP servers with write/send tools.
WRITE_TOOLS: frozenset[str] = frozenset({
    # smb-mcp
    "smb_write_file", "smb_delete", "smb_move", "smb_copy", "smb_mkdir",
    # mcp-server-filesystem
    "write_file", "edit_file", "create_directory", "move_file",
    # messaging / email
    "send_email", "send_message", "send_whatsapp",
})


def load_config(path: str | None = None) -> AriaConfig:
    config_path = Path(path or os.getenv("ARIA_CONFIG", "aria.config.json"))

    if not config_path.exists():
        return AriaConfig(mcp_servers={}, roles={"default": Role(name="default")})

    raw = json.loads(config_path.read_text())

    servers: dict[str, McpServerConfig] = {
        name: McpServerConfig(
            command=cfg["command"],
            transport=cfg.get("transport", "stdio"),
            args=cfg.get("args", []),
            env=cfg.get("env", {}),
        )
        for name, cfg in raw.get("mcpServers", {}).items()
    }

    # Support both "roles" (current) and "profiles" (legacy) config keys.
    roles_raw = raw.get("roles") or raw.get("profiles") or {}
    roles: dict[str, Role] = {
        name: Role(
            name=name,
            model=p.get("model"),
            servers=p.get("servers", list(servers)),
            readonly=p.get("readonly", False),
            description=p.get("description", ""),
        )
        for name, p in roles_raw.items()
    }

    if "default" not in roles:
        roles["default"] = Role(name="default", servers=list(servers))

    return AriaConfig(mcp_servers=servers, roles=roles)
