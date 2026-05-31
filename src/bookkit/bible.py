"""The story bible — canonical, structured continuity data for a book.

A ``bible.yaml`` is the single source of truth a book is generated against:
characters (with their voice and mutable status), the world, the timeline, and the
per-chapter plot beats. It is plain, committed, validated data — continuity lives
in source control, not in a model's memory. See docs/continuity.md.
"""

from __future__ import annotations

from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Relationship(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # "with" is a Python keyword, so the field is with_ and aliased on load/dump.
    with_: str = Field(alias="with")
    nature: str = ""


class StateChange(BaseModel):
    """A canonical mutation caused by a chapter.

    Accepts a structured form ({character, set}) or a bare string (free-text note),
    so authors and weaker models can both express state changes naturally.
    """

    character: str = ""
    set: dict[str, Any] = {}
    note: str = ""

    @field_validator("set", mode="before")
    @classmethod
    def _none_to_empty(cls, v: Any) -> Any:
        return v or {}


class Character(BaseModel):
    name: str
    aka: list[str] = []
    role: str = ""
    description: str = ""
    voice: str = ""  # pasted verbatim into chapter prompts to keep dialogue consistent
    relationships: list[Relationship] = []
    arc: str = ""
    status: str = "alive"  # mutable canon: alive | dead | departed | active | unknown | ...
    first_appears: int | None = None


class WorldFact(BaseModel):
    id: str = ""
    fact: str
    tags: list[str] = []


class TimelineEntry(BaseModel):
    when: str = ""
    event: str


class Beat(BaseModel):
    """One chapter's entry in the plot spine — both a writing brief and a contract."""

    chapter: int
    summary: str = ""
    advances: list[str] = []
    state_changes: list[StateChange] = []

    @field_validator("state_changes", mode="before")
    @classmethod
    def _coerce_state_changes(cls, v: Any) -> Any:
        """Allow bare strings in state_changes: 'X happened' -> {note: 'X happened'}."""
        if not v:
            return []
        out: list[Any] = []
        for item in v:
            if isinstance(item, str):
                out.append({"note": item})
            else:
                out.append(item)
        return out


class BibleConfig(BaseModel):
    title: str = ""
    logline: str = ""
    themes: list[str] = []
    world: list[WorldFact] = []
    timeline: list[TimelineEntry] = []
    characters: list[Character] = []
    beats: list[Beat] = []

    def character(self, name: str) -> Character | None:
        """Look up a character by name or alias, case-insensitively."""
        key = name.strip().lower()
        for c in self.characters:
            if c.name.strip().lower() == key or key in {a.strip().lower() for a in c.aka}:
                return c
        return None

    def beat_for(self, chapter: int) -> Beat | None:
        for b in self.beats:
            if b.chapter == chapter:
                return b
        return None

    def apply_state_changes(self, chapter: int, changes: list[StateChange]) -> None:
        """Record canonical changes on a chapter's beat and propagate to characters.

        The beat (created if missing) gets the changes appended; any ``set`` keys
        on a named, known character also update that character's live canon (e.g.
        ``status``) so later chapters see the new state.
        """
        beat = self.beat_for(chapter)
        if beat is None:
            beat = Beat(chapter=chapter)
            self.beats.append(beat)
            self.beats.sort(key=lambda b: b.chapter)
        beat.state_changes.extend(changes)
        for change in changes:
            if not change.character or not change.set:
                continue
            character = self.character(change.character)
            if character is None:
                continue
            for key, value in change.set.items():
                if hasattr(character, key):
                    setattr(character, key, value)


def load_bible(path: Any) -> BibleConfig:
    """Load and validate a bible.yaml file into a BibleConfig."""
    from pathlib import Path

    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return BibleConfig.model_validate(raw)


def dump_bible(bible: BibleConfig) -> str:
    """Serialize a BibleConfig back to YAML (aliases honored, empties dropped)."""
    data = bible.model_dump(by_alias=True, exclude_defaults=True)
    return yaml.dump(data, allow_unicode=True, sort_keys=False)
