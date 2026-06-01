from __future__ import annotations

from .base import Backend
from .chatterbox import ChatterboxBackend
from .elevenlabs import ElevenLabsBackend
from .kokoro import KokoroBackend
from .openai_tts import OpenAIBackend

__all__ = [
    "Backend",
    "ChatterboxBackend",
    "ElevenLabsBackend",
    "KokoroBackend",
    "OpenAIBackend",
    "get_backend",
]


def get_backend(name: str) -> Backend:
    """Return a Backend instance for the given backend name."""
    if name == "chatterbox":
        return ChatterboxBackend()
    if name == "elevenlabs":
        return ElevenLabsBackend()
    if name == "kokoro":
        return KokoroBackend()
    if name == "openai":
        return OpenAIBackend()
    raise ValueError(
        f"Unknown backend: {name!r}. Valid choices are: chatterbox, elevenlabs, kokoro, openai."
    )
