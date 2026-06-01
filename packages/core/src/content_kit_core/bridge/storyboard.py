"""The visual bridge contract: ``storyboard.json``.

The visual-tier sibling of the audio bridge. A *script producer* (today
``bookkit storyboard``) emits an ordered list of panels per chapter — scene,
dialogue, characters present, and art-direction notes — and a *visual renderer*
(a comic generator, a video/animatic tool) consumes the same ``storyboard.json``
the way the audio renderer consumes ``script.json``. One canonical source, many
rendered media. These are the data shapes; the planning logic that fills them
lives in whichever tool produces the storyboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Panel:
    id: str
    scene: str  # narration / description for the panel
    dialogue: list[dict] = field(default_factory=list)  # [{character, text}]
    characters: list[str] = field(default_factory=list)  # present, for art consistency
    art_notes: list[str] = field(default_factory=list)  # appearance cues from the bible


@dataclass
class StoryboardChapter:
    name: str  # output sub-directory, e.g. "chapter_01"
    title: str
    panels: list[Panel] = field(default_factory=list)


@dataclass
class Storyboard:
    project: str
    chapters: list[StoryboardChapter]

    @property
    def panel_count(self) -> int:
        return sum(len(c.panels) for c in self.chapters)


__all__ = ["Panel", "StoryboardChapter", "Storyboard"]
