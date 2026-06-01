"""Canonical cross-tool bridge contracts.

A bridge is a written artifact one tool produces and another consumes. Keeping
the schema here — imported by both sides — means the producer and the consumer
validate against the *same* model, so the contract cannot silently drift.
"""

from __future__ import annotations

from .episode import (
    Anchor,
    BgTrack,
    EpisodeConfig,
    ScriptLine,
    SfxHit,
    TimelineEntry,
    VoiceConfig,
    validate_episode,
    validate_script,
)
from .storyboard import Panel, Storyboard, StoryboardChapter

__all__ = [
    # audio bridge
    "VoiceConfig",
    "TimelineEntry",
    "Anchor",
    "BgTrack",
    "SfxHit",
    "EpisodeConfig",
    "ScriptLine",
    "validate_episode",
    "validate_script",
    # visual bridge
    "Panel",
    "StoryboardChapter",
    "Storyboard",
]
