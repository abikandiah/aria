"""Tests for config loading and WRITE_TOOLS."""
from __future__ import annotations

import json
import os
import tempfile

import pytest

from aria.config import AriaConfig, McpServerConfig, Role, WRITE_TOOLS, load_config


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


# ---------------------------------------------------------------------------
# WRITE_TOOLS
# ---------------------------------------------------------------------------

def test_write_tools_contains_smb_writes():
    assert "smb_write_file" in WRITE_TOOLS
    assert "smb_delete" in WRITE_TOOLS
    assert "smb_move" in WRITE_TOOLS


def test_write_tools_contains_filesystem_writes():
    assert "write_file" in WRITE_TOOLS
    assert "edit_file" in WRITE_TOOLS
    assert "create_directory" in WRITE_TOOLS
    assert "move_file" in WRITE_TOOLS


def test_write_tools_contains_messaging():
    assert "send_email" in WRITE_TOOLS
    assert "send_message" in WRITE_TOOLS


def test_write_tools_excludes_reads():
    assert "read_file" not in WRITE_TOOLS
    assert "list_directory" not in WRITE_TOOLS
    assert "search_files" not in WRITE_TOOLS


def test_readonly_filter_removes_write_tools():
    class _Tool:
        def __init__(self, name): self.name = name

    all_tools = [_Tool(n) for n in ["read_file", "write_file", "smb_write_file", "list_directory"]]
    filtered = [t for t in all_tools if t.name not in WRITE_TOOLS]
    names = {t.name for t in filtered}
    assert names == {"read_file", "list_directory"}


def test_readonly_filter_keeps_all_tools_when_not_readonly():
    class _Tool:
        def __init__(self, name): self.name = name

    all_tools = [_Tool(n) for n in ["read_file", "write_file"]]
    filtered = all_tools  # readonly=False → no filter applied
    assert len(filtered) == 2
