"""The series bible — canon shared across several correlated books.

A ``series.yaml`` sits at a collection's root, above the per-book ``bible.yaml``
files. It carries the cross-book arc, a shared cast, and each book's role and
ending state, so book N is written knowing how book N-1 left things. See
docs/continuity.md §4.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator

from .bible import BibleConfig, Character, StateChange, coerce_state_changes


class SeriesBookEntry(BaseModel):
    dir: str  # the book's directory name, relative to the collection root
    title: str = ""
    role: str = ""  # e.g. setup | escalation | resolution
    opens_from: str | None = None  # dir of the predecessor book this one continues
    ends_with_state: list[StateChange] = []  # canonical hand-off to the next book

    @field_validator("ends_with_state", mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> Any:
        return coerce_state_changes(v)


class SeriesConfig(BaseModel):
    series: str = ""
    arc: str = ""
    shared_characters: list[Character] = []  # cast carried across the whole series
    books: list[SeriesBookEntry] = []

    def book(self, dir_name: str) -> SeriesBookEntry | None:
        for entry in self.books:
            if entry.dir == dir_name:
                return entry
        return None


def load_series(path: Any) -> SeriesConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return SeriesConfig.model_validate(raw)


def dump_series(series: SeriesConfig) -> str:
    data = series.model_dump(by_alias=True, exclude_defaults=True)
    return yaml.dump(data, allow_unicode=True, sort_keys=False)


def merge_shared_characters(series: SeriesConfig, bible: BibleConfig) -> BibleConfig:
    """Return a bible with the series' shared cast folded in.

    A book's own characters win by name; shared characters not present locally are
    appended. This gives every book the full cast even when its local bible is
    sparse, without overriding book-specific canon.
    """
    existing = {c.name.strip().lower() for c in bible.characters}
    extra = [c for c in series.shared_characters if c.name.strip().lower() not in existing]
    if not extra:
        return bible
    return bible.model_copy(update={"characters": bible.characters + extra})


def series_context_text(series: SeriesConfig, dir_name: str) -> str:
    """Render the cross-book context for the book at ``dir_name``.

    Includes the series arc and, if this book continues another, the predecessor's
    ending state — so the model knows where the story stands as this book opens.
    """
    lines: list[str] = []
    if series.series:
        lines.append(f"SERIES: {series.series}")
    if series.arc:
        lines.append(f"ARC: {series.arc}")

    entry = series.book(dir_name)
    if entry and entry.opens_from:
        prev = series.book(entry.opens_from)
        if prev:
            label = prev.title or prev.dir
            role = f" ({prev.role})" if prev.role else ""
            lines.append(f"\nThis book follows '{label}'{role}, which ended with:")
            for sc in prev.ends_with_state:
                prefix = f"{sc.character}: " if sc.character else ""
                lines.append(f"  - {prefix}{sc.set or sc.note}")
    return "\n".join(lines).strip()
