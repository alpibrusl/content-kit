from __future__ import annotations

import os

from .base import Writer

#: Built-in fallback default. Kept local + keyless so bookkit runs offline out of
#: the box. It is only a default, never an assumption — see docs/continuity.md §10.
_FALLBACK_WRITER = "ollama"


def default_writer_name() -> str:
    """Resolve the default writer backend, env-overridable, no hardcoded vendor."""
    return os.environ.get("BOOKKIT_WRITER", _FALLBACK_WRITER)


def get_writer(name: str, model: str | None = None) -> Writer:
    """Return a Writer instance for the given backend name.

    Every AI-assisted flow goes through this factory, so the tool stays
    LLM-agnostic: adding a provider means adding one Writer subclass here.
    """
    if name == "ollama":
        from .ollama import OllamaWriter

        return OllamaWriter(model=model or "llama3.2")
    if name == "claude":
        from .claude import ClaudeWriter

        return ClaudeWriter(model=model or "claude-opus-4-7")
    if name == "openai":
        from .openai_writer import OpenAIWriter

        return OpenAIWriter(model=model or "gpt-4o")
    if name in ("openai_compat", "compat", "openai-compatible"):
        from .openai_compat import OpenAICompatWriter

        return OpenAICompatWriter(model=model)
    raise ValueError(
        f"Unknown writer backend: {name!r}. Valid choices are: "
        "claude, ollama, openai, openai_compat."
    )


__all__ = ["Writer", "get_writer", "default_writer_name"]
