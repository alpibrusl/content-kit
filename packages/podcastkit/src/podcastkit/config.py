"""Episode configuration — the audio bridge contract from content_kit_core.

``EpisodeConfig`` and friends define the ``episode.yaml`` shape this renderer
consumes and a producer (e.g. ``bookkit audiobook``) emits. The models live in
the shared core so both sides validate against one contract. Kept as a module so
existing ``from .config import EpisodeConfig`` / ``from ..config import
VoiceConfig`` sites are unchanged.
"""

from __future__ import annotations

from content_kit_core.bridge.episode import (
    Anchor,
    BgTrack,
    EpisodeConfig,
    SfxHit,
    TimelineEntry,
    VoiceConfig,
)

__all__ = [
    "Anchor",
    "BgTrack",
    "EpisodeConfig",
    "SfxHit",
    "TimelineEntry",
    "VoiceConfig",
]
