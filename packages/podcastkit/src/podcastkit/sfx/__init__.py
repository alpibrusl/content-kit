"""SFX and music generation via Meta AudioCraft (AudioGen / MusicGen)."""

from __future__ import annotations

from ._audiocraft import generate_music, generate_sfx

__all__ = ["generate_sfx", "generate_music"]
