"""The audio bridge contract: ``episode.yaml`` + ``script.json``.

This is the single source of truth for the artifact that crosses the seam
between a *script producer* (e.g. ``bookkit audiobook``, which turns a book into
a podcastkit project) and the *audio renderer* (``podcastkit assemble``, which
mixes it to MP3). Both sides import these models from here, so the contract
cannot drift: a producer validates what it writes against the very models the
consumer validates what it reads. The link stays a data artifact, not a call.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from .._errors import PreconditionError


class VoiceConfig(BaseModel):
    backend: Literal["chatterbox", "elevenlabs", "kokoro", "openai"]
    voice_id: str  # ElevenLabs voice_id, Kokoro voice name, or OpenAI voice name
    model_id: str = ""  # ElevenLabs model_id; unused for others
    settings: dict[str, Any] = {}  # ElevenLabs voice_settings; unused for others


class TimelineEntry(BaseModel):
    id: str
    pre_silence: float = 0.5


# anchor: [line_id, "start"|"end", offset_seconds]
Anchor = tuple[str, Literal["start", "end"], float]


class BgTrack(BaseModel):
    file: str
    start: Anchor
    fade_in: float = 2.0
    fade_out_at: Anchor
    fade_out_dur: float = 2.0
    volume_db: float = -25.0
    loop: bool = True


class SfxHit(BaseModel):
    file: str
    at: Anchor
    volume: float = 0.6


class EpisodeConfig(BaseModel):
    title: str = ""
    output: str = "episode.mp3"
    voices: dict[str, VoiceConfig]
    timeline: list[TimelineEntry]
    bg_tracks: list[BgTrack] = []
    sfx_hits: list[SfxHit] = []


class ScriptLine(BaseModel):
    """One entry in ``script.json`` — the spoken unit the renderer voices."""

    id: str
    character: str
    text: str


def validate_episode(doc: dict[str, Any]) -> EpisodeConfig:
    """Validate an ``episode.yaml`` document against the bridge contract.

    Producers call this on what they are about to write, so an incompatible
    change to the contract surfaces in the *producer's* own tests rather than as
    a cryptic failure when the renderer later loads the file. Re-raised as a
    :class:`PreconditionError` with an actionable hint.
    """
    try:
        return EpisodeConfig.model_validate(doc)
    except ValidationError as exc:
        raise PreconditionError(
            f"episode does not satisfy the audio bridge contract: {exc.error_count()} error(s)",
            hint="The producer emitted an episode.yaml shape podcastkit cannot render. "
            "See content_kit_core.bridge.EpisodeConfig for the required fields.",
        ) from exc


def validate_script(entries: list[dict[str, Any]]) -> list[ScriptLine]:
    """Validate a ``script.json`` line list against the bridge contract."""
    try:
        return [ScriptLine.model_validate(entry) for entry in entries]
    except ValidationError as exc:
        raise PreconditionError(
            f"script.json does not satisfy the audio bridge contract: {exc.error_count()} error(s)",
            hint="Each line must be an object with id, character, and text.",
        ) from exc


__all__ = [
    "VoiceConfig",
    "TimelineEntry",
    "Anchor",
    "BgTrack",
    "SfxHit",
    "EpisodeConfig",
    "ScriptLine",
    "validate_episode",
    "validate_script",
]
