"""The story bible — re-exported from content_kit_core.canon.

The canon model (characters, world, timeline, plot beats) lives in the shared
core so every tier — prose, audio, the storyboard's art notes, and future
media — reads a book against the *same* committed continuity data. Kept as a
module so existing ``from .bible import ...`` sites are unchanged.
"""

from __future__ import annotations

from content_kit_core.canon import (
    Beat,
    BibleConfig,
    Character,
    Relationship,
    StateChange,
    TimelineEntry,
    WorldFact,
    coerce_state_changes,
    dump_bible,
    load_bible,
)

__all__ = [
    "Beat",
    "BibleConfig",
    "Character",
    "Relationship",
    "StateChange",
    "TimelineEntry",
    "WorldFact",
    "coerce_state_changes",
    "dump_bible",
    "load_bible",
]
