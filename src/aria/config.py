"""Load Aria configuration from aria.config.json.

Config file format mirrors Claude Desktop's MCP server format so configs
are portable between tools. Profiles layer model and permission settings
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
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class Profile:
    name: str
    model: str | None = None
    servers: list[str] = field(default_factory=list)
    readonly: bool = False
    description: str = ""


@dataclass
class AriaConfig:
    mcp_servers: dict[str, McpServerConfig]
    profiles: dict[str, Profile]


def load_config(path: str | None = None) -> AriaConfig:
    config_path = Path(path or os.getenv("ARIA_CONFIG", "aria.config.json"))

    if not config_path.exists():
        return AriaConfig(mcp_servers={}, profiles={"default": Profile(name="default")})

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

    profiles: dict[str, Profile] = {
        name: Profile(
            name=name,
            model=p.get("model"),
            servers=p.get("servers", list(servers)),
            readonly=p.get("readonly", False),
            description=p.get("description", ""),
        )
        for name, p in raw.get("profiles", {}).items()
    }

    if "default" not in profiles:
        profiles["default"] = Profile(name="default", servers=list(servers))

    return AriaConfig(mcp_servers=servers, profiles=profiles)
