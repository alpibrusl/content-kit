from __future__ import annotations

from .base import Writer


def get_writer(name: str, model: str | None = None) -> Writer:
    """Return a Writer instance for the given backend name."""
    if name == "ollama":
        from .ollama import OllamaWriter

        return OllamaWriter(model=model or "llama3.2")
    if name == "claude":
        from .claude import ClaudeWriter

        return ClaudeWriter(model=model or "claude-opus-4-7")
    if name == "openai":
        from .openai_writer import OpenAIWriter

        return OpenAIWriter(model=model or "gpt-4o")
    raise ValueError(
        f"Unknown writer backend: {name!r}. Valid choices are: claude, ollama, openai."
    )


__all__ = ["Writer", "get_writer"]
