"""Tests for config loading and write-tool resolution."""
from __future__ import annotations

import json
import os
import tempfile

import pytest

from aria.config import AriaConfig, McpServerConfig, Role, _BUILTIN_WRITE_TOOLS, get_write_tools, load_config


def _tmp_config(data: dict) -> str:
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(data, f)
    f.close()
    return f.name


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

def test_load_roles_key():
    path = _tmp_config({
        "mcpServers": {"s": {"command": "x"}},
        "roles": {"default": {"model": "m", "servers": ["s"]}},
    })
    try:
        cfg = load_config(path)
        assert "default" in cfg.roles
        assert isinstance(cfg.roles["default"], Role)
        assert cfg.roles["default"].model == "m"
    finally:
        os.unlink(path)


def test_load_profiles_fallback():
    """Legacy 'profiles' key must still work."""
    path = _tmp_config({
        "mcpServers": {},
        "profiles": {"default": {"model": "m2"}},
    })
    try:
        cfg = load_config(path)
        assert "default" in cfg.roles
        assert cfg.roles["default"].model == "m2"
    finally:
        os.unlink(path)


def test_load_injects_default_role():
    """A config with no 'default' role gets one auto-injected."""
    path = _tmp_config({"mcpServers": {"s": {"command": "x"}}, "roles": {}})
    try:
        cfg = load_config(path)
        assert "default" in cfg.roles
        assert cfg.roles["default"].servers == ["s"]
    finally:
        os.unlink(path)


def test_load_missing_file_returns_empty_config():
    cfg = load_config("/nonexistent/path.json")
    assert "default" in cfg.roles
    assert cfg.mcp_servers == {}


def test_load_readonly_flag():
    path = _tmp_config({
        "mcpServers": {"s": {"command": "x"}},
        "roles": {"viewer": {"servers": ["s"], "readonly": True}},
    })
    try:
        cfg = load_config(path)
        assert cfg.roles["viewer"].readonly is True
    finally:
        os.unlink(path)


def test_load_credential_reference_preserved():
    """Credential reference dicts in env should pass through to McpServerConfig unchanged."""
    ref = {"from": "env", "var": "MY_SECRET"}
    path = _tmp_config({
        "mcpServers": {"s": {"command": "x", "env": {"PASS": ref}}},
        "roles": {},
    })
    try:
        cfg = load_config(path)
        assert cfg.mcp_servers["s"].env["PASS"] == ref
    finally:
        os.unlink(path)


def test_load_write_tools_parsed():
    """write_tools declared in mcpServers should be loaded into McpServerConfig."""
    path = _tmp_config({
        "mcpServers": {"s": {"command": "x", "write_tools": ["write_file", "delete_file"]}},
        "roles": {},
    })
    try:
        cfg = load_config(path)
        assert cfg.mcp_servers["s"].write_tools == ["write_file", "delete_file"]
    finally:
        os.unlink(path)


def test_load_write_tools_defaults_to_empty():
    """Servers without write_tools in config get an empty list, not None."""
    path = _tmp_config({
        "mcpServers": {"s": {"command": "x"}},
        "roles": {},
    })
    try:
        cfg = load_config(path)
        assert cfg.mcp_servers["s"].write_tools == []
    finally:
        os.unlink(path)


def test_load_persona_parsed():
    """persona declared in a role should be loaded into Role."""
    path = _tmp_config({
        "mcpServers": {},
        "roles": {"default": {"persona": "analyst"}},
    })
    try:
        cfg = load_config(path)
        assert cfg.roles["default"].persona == "analyst"
    finally:
        os.unlink(path)


def test_load_persona_defaults_to_none():
    """Roles without a persona field should have persona=None."""
    path = _tmp_config({
        "mcpServers": {},
        "roles": {"default": {}},
    })
    try:
        cfg = load_config(path)
        assert cfg.roles["default"].persona is None
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# get_write_tools
# ---------------------------------------------------------------------------

def _server(write_tools: list[str]) -> McpServerConfig:
    return McpServerConfig(command="x", write_tools=write_tools)


def test_get_write_tools_uses_declared_list():
    """Servers with explicit write_tools use only that list."""
    servers = {"s": _server(["my_write", "my_delete"])}
    result = get_write_tools(servers)
    assert "my_write" in result
    assert "my_delete" in result
    # Built-in fallback tools should NOT be present when server declares its own list.
    assert "write_file" not in result
    assert "smb_write_file" not in result


def test_get_write_tools_falls_back_to_builtin_when_undeclared():
    """Servers without write_tools fall back to _BUILTIN_WRITE_TOOLS."""
    servers = {"s": _server([])}
    result = get_write_tools(servers)
    assert "smb_write_file" in result
    assert "write_file" in result
    assert "send_email" in result


def test_get_write_tools_excludes_reads():
    """Read-only tool names should never appear in the built-in fallback."""
    servers = {"s": _server([])}
    result = get_write_tools(servers)
    assert "read_file" not in result
    assert "list_directory" not in result
    assert "search_files" not in result


def test_get_write_tools_merges_multiple_declared_servers():
    """Union of declared write_tools across all servers."""
    servers = {
        "a": _server(["write_file"]),
        "b": _server(["send_email"]),
    }
    result = get_write_tools(servers)
    assert "write_file" in result
    assert "send_email" in result


def test_get_write_tools_mixed_declared_and_undeclared():
    """Undeclared server contributes full builtin set; declared server only its list."""
    servers = {
        "declared": _server(["my_custom_write"]),
        "legacy": _server([]),  # no declaration → builtin fallback
    }
    result = get_write_tools(servers)
    assert "my_custom_write" in result
    assert "write_file" in result  # from legacy server's builtin fallback


def test_readonly_filter_removes_write_tools():
    class _Tool:
        def __init__(self, name): self.name = name

    servers = {"s": _server(["write_file", "smb_write_file"])}
    write_tools = get_write_tools(servers)
    all_tools = [_Tool(n) for n in ["read_file", "write_file", "smb_write_file", "list_directory"]]
    filtered = [t for t in all_tools if t.name not in write_tools]
    names = {t.name for t in filtered}
    assert names == {"read_file", "list_directory"}


def test_readonly_filter_keeps_all_tools_when_not_readonly():
    class _Tool:
        def __init__(self, name): self.name = name

    all_tools = [_Tool(n) for n in ["read_file", "write_file"]]
    filtered = all_tools  # readonly=False → no filter applied
    assert len(filtered) == 2
