from __future__ import annotations

import os

from .base import Writer

#: Built-in fallback default. Kept local + keyless so the platform runs offline
#: out of the box. It is only a default, never an assumption.
_FALLBACK_WRITER = "ollama"

#: Canonical env var first; the per-tool legacy names are honored for
#: back-compat so existing setups keep working after the consolidation.
_WRITER_ENV_VARS = ("CONTENTKIT_WRITER", "BOOKKIT_WRITER", "PODCASTKIT_WRITER")


def default_writer_name() -> str:
    """Resolve the default writer backend, env-overridable, no hardcoded vendor."""
    for var in _WRITER_ENV_VARS:
        value = os.environ.get(var)
        if value:
            return value
    return _FALLBACK_WRITER


def get_writer(name: str, model: str | None = None) -> Writer:
    """Return a Writer instance for the given backend name.

    Every AI-assisted flow in every tool goes through this one factory, so the
    platform stays LLM-agnostic: adding a provider means adding one Writer
    subclass here, once, for all tools.
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
