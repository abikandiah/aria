"""Model factory — creates any LangChain-compatible chat model from a name string.

Two paths:
  - OPENAI_BASE_URL set → ChatOpenAI pointed at that endpoint.
    Covers OpenRouter, Ollama, LM Studio, vLLM, and any OpenAI-compatible API.
  - No base URL → init_chat_model for direct provider access
    (Anthropic, OpenAI, Google, etc. via their own SDKs).

Model name examples:
  claude-sonnet-4-6              direct Anthropic
  anthropic/claude-sonnet-4-6    OpenRouter-style (use with OPENAI_BASE_URL)
  openai:gpt-4o                  direct OpenAI via init_chat_model
  llama3.1:8b                    Ollama local (use with OPENAI_BASE_URL)
"""
from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel

_DEFAULT_MODEL = "claude-sonnet-4-6"
_DEFAULT_MAX_TOKENS = 8096


def _max_tokens() -> int:
    raw = os.getenv("ARIA_MAX_TOKENS")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return _DEFAULT_MAX_TOKENS


def create_model(name: str | None = None) -> BaseChatModel:
    """Return a chat model instance for the given name (or env/default)."""
    model_name = name or os.getenv("ARIA_MODEL") or _DEFAULT_MODEL
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
    max_tokens = _max_tokens()

    if base_url:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model_name,
            base_url=base_url,
            max_tokens=max_tokens,
        )

    from langchain.chat_models import init_chat_model
    return init_chat_model(model_name, max_tokens=max_tokens)
