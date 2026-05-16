"""Tests for credential resolver, persona loader, and agent construction."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from aria.agent import _resolve_env, load_persona


# ---------------------------------------------------------------------------
# _resolve_env — plain strings
# ---------------------------------------------------------------------------

def test_plain_strings_pass_through():
    assert _resolve_env({"FOO": "bar", "EMPTY": ""}) == {"FOO": "bar", "EMPTY": ""}


def test_empty_env_returns_empty():
    assert _resolve_env({}) == {}


# ---------------------------------------------------------------------------
# _resolve_env — env-var references
# ---------------------------------------------------------------------------

def test_env_ref_resolved(monkeypatch):
    monkeypatch.setenv("MY_SECRET", "hunter2")
    result = _resolve_env({"PASS": {"from": "env", "var": "MY_SECRET"}})
    assert result["PASS"] == "hunter2"


def test_env_ref_missing_var_raises(monkeypatch):
    monkeypatch.delenv("DEFINITELY_NOT_SET", raising=False)
    with pytest.raises(ValueError, match="not set"):
        _resolve_env({"X": {"from": "env", "var": "DEFINITELY_NOT_SET"}})


def test_env_ref_missing_var_field_raises():
    with pytest.raises(ValueError, match="missing the 'var' field"):
        _resolve_env({"X": {"from": "env"}})


# ---------------------------------------------------------------------------
# _resolve_env — keychain references
# ---------------------------------------------------------------------------

def test_keychain_missing_service_field_raises():
    with pytest.raises(ValueError, match="missing fields"):
        _resolve_env({"X": {"from": "keychain", "key": "password"}})  # no "service"


def test_keychain_missing_key_field_raises():
    with pytest.raises(ValueError, match="missing fields"):
        _resolve_env({"X": {"from": "keychain", "service": "aria-nas"}})  # no "key"


def test_keychain_missing_both_fields_raises():
    with pytest.raises(ValueError, match="missing fields"):
        _resolve_env({"X": {"from": "keychain"}})


# ---------------------------------------------------------------------------
# _resolve_env — error cases
# ---------------------------------------------------------------------------

def test_unknown_source_raises():
    with pytest.raises(ValueError, match="Unknown credential source"):
        _resolve_env({"X": {"from": "magic"}})


def test_invalid_value_type_raises():
    with pytest.raises(ValueError, match="Invalid credential value type"):
        _resolve_env({"X": 42})  # type: ignore[arg-type]


def test_invalid_value_list_raises():
    with pytest.raises(ValueError, match="Invalid credential value type"):
        _resolve_env({"X": ["a", "b"]})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# load_persona
# ---------------------------------------------------------------------------

def test_load_persona_none_returns_default():
    """load_persona(None) must return a non-empty string (the built-in default)."""
    result = load_persona(None)
    assert isinstance(result, str)
    assert len(result) > 0


def test_load_persona_builtin_name():
    """Built-in persona names ('browse', 'analyst') resolve without a path."""
    browse = load_persona("browse")
    analyst = load_persona("analyst")
    assert "read-only" in browse.lower()
    assert "analyst" in analyst.lower()


def test_load_persona_builtin_name_with_extension():
    """'browse.md' should resolve the same as 'browse'."""
    assert load_persona("browse.md") == load_persona("browse")


def test_load_persona_file_path(tmp_path):
    """A path to an existing file is read directly."""
    persona_file = tmp_path / "custom.md"
    persona_file.write_text("You are a custom assistant.")
    result = load_persona(str(persona_file))
    assert result == "You are a custom assistant."


def test_load_persona_missing_raises():
    """A path or name that can't be resolved raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="Persona not found"):
        load_persona("nonexistent_persona_xyz")


# ---------------------------------------------------------------------------
# make_agent — sync, returns a compiled graph
# ---------------------------------------------------------------------------

def test_make_agent_is_sync():
    """make_agent must be a regular function, not a coroutine function."""
    import inspect
    from aria.agent import make_agent
    assert not inspect.iscoroutinefunction(make_agent), (
        "make_agent should be sync — create_react_agent is synchronous"
    )


def test_make_agent_returns_graph():
    """make_agent returns a compiled LangGraph graph (has ainvoke)."""
    from unittest.mock import MagicMock
    from aria.agent import make_agent

    model = MagicMock()
    model.bind_tools = MagicMock(return_value=model)
    agent = make_agent(model, [])
    assert hasattr(agent, "ainvoke")
    assert hasattr(agent, "astream_events")
