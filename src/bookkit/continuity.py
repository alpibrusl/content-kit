"""Continuity checking — a linter for the canon (docs/continuity.md §5).

Deterministic, dependency-free rules that catch the common ways a book or series
drifts from its own bible: a dead/departed character reappearing, name drift,
beats that don't line up with the chapters, and broken series hand-offs. An
optional LLM pass (driven from the CLI) complements these; this module is the
cheap, always-on first pass.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._context import find_chapter_file
from .bible import BibleConfig
from .config import BookConfig
from .series import SeriesConfig

# Statuses that mean a character should no longer appear unless explicitly revived.
INACTIVE = {"dead", "departed", "gone", "deceased", "killed"}


@dataclass
class Finding:
    severity: str  # "error" | "warning"
    kind: str
    detail: str
    chapter: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "kind": self.kind,
            "detail": self.detail,
            "chapter": self.chapter,
        }


def _canonical_names(bible: BibleConfig) -> dict[str, str]:
    """Map lowercased name -> canonical name, for non-empty characters."""
    return {c.name.strip().lower(): c.name.strip() for c in bible.characters if c.name.strip()}


def _inactive_chapters(bible: BibleConfig) -> dict[str, tuple[int, str]]:
    """Per character, the chapter from which they are inactive and the status name.

    Built from the initial character status and from beat state_changes in order; a
    later change to an active status revives the character (clears the entry).
    """
    inactive: dict[str, tuple[int, str]] = {}
    for c in bible.characters:
        if c.name.strip() and c.status and c.status.lower() in INACTIVE:
            inactive[c.name] = (c.first_appears or 1, c.status.lower())
    for beat in sorted(bible.beats, key=lambda b: b.chapter):
        for sc in beat.state_changes:
            if not sc.character or not sc.set:
                continue
            status = str(sc.set.get("status", "")).lower()
            if status in INACTIVE:
                inactive[sc.character] = (beat.chapter, status)
            elif status and sc.character in inactive:
                inactive.pop(sc.character, None)
    return inactive


def check_book(
    bible: BibleConfig,
    config: BookConfig | None = None,
    book_dir: Path | None = None,
    scan_prose: bool = False,
) -> list[Finding]:
    """Run the deterministic book-level continuity rules."""
    findings: list[Finding] = []
    names = _canonical_names(bible)

    n_chapters = (
        len(config.chapters) if config else max((b.chapter for b in bible.beats), default=0)
    )

    # Duplicate beats for the same chapter.
    counts: dict[int, int] = {}
    for beat in bible.beats:
        counts[beat.chapter] = counts.get(beat.chapter, 0) + 1
    for chapter, count in sorted(counts.items()):
        if count > 1:
            findings.append(
                Finding(
                    "error", "duplicate-beat", f"{count} beats define chapter {chapter}", chapter
                )
            )

    # Beats out of range / missing beats (only when we know the chapter count).
    if n_chapters:
        for beat in bible.beats:
            if beat.chapter < 1 or beat.chapter > n_chapters:
                findings.append(
                    Finding(
                        "warning",
                        "beat-out-of-range",
                        f"beat for chapter {beat.chapter}, but the book has {n_chapters} chapters",
                        beat.chapter,
                    )
                )
        present = {b.chapter for b in bible.beats}
        for n in range(1, n_chapters + 1):
            if n not in present:
                findings.append(Finding("warning", "missing-beat", f"no beat for chapter {n}", n))

    # State changes referencing a character not in the bible (likely name drift).
    for beat in bible.beats:
        for sc in beat.state_changes:
            if sc.character and sc.character.strip() and sc.character.lower() not in names:
                close = difflib.get_close_matches(
                    sc.character.lower(), list(names), n=1, cutoff=0.8
                )
                hint = f" (did you mean '{names[close[0]]}'?)" if close else ""
                findings.append(
                    Finding(
                        "warning",
                        "unknown-character",
                        f"state_change references '{sc.character}' not in the bible{hint}",
                        beat.chapter,
                    )
                )

    # Dead/departed character reappearing in a later beat (or, with scan_prose, prose).
    flagged: set[tuple[str, int]] = set()
    for name, (since, status) in _inactive_chapters(bible).items():
        char = bible.character(name)
        canonical = names.get(name.lower(), name)
        aliases = [canonical, *(char.aka if char else [])]
        for beat in bible.beats:
            if beat.chapter <= since:
                continue
            haystack = " ".join([beat.summary, *beat.advances]).lower()
            if any(a and a.lower() in haystack for a in aliases):
                findings.append(
                    Finding(
                        "error",
                        "revenant",
                        f"{canonical} is {status} as of chapter {since} but appears in "
                        f"chapter {beat.chapter}'s beat",
                        beat.chapter,
                    )
                )
                flagged.add((canonical, beat.chapter))
        if scan_prose and book_dir:
            for beat in bible.beats:
                if beat.chapter <= since or (canonical, beat.chapter) in flagged:
                    continue
                path = find_chapter_file(book_dir, beat.chapter)
                if not path:
                    continue
                text = path.read_text(encoding="utf-8").lower()
                if any(a and a.lower() in text for a in aliases):
                    findings.append(
                        Finding(
                            "error",
                            "revenant",
                            f"{canonical} ({status} since chapter {since}) appears in "
                            f"chapter {beat.chapter}'s text",
                            beat.chapter,
                        )
                    )
    return findings


def check_series(series: SeriesConfig) -> list[Finding]:
    """Run the deterministic series-level continuity rules."""
    findings: list[Finding] = []
    dirs = {b.dir for b in series.books}
    for book in series.books:
        if book.opens_from and book.opens_from == book.dir:
            findings.append(
                Finding("error", "self-handoff", f"book '{book.dir}' opens_from itself")
            )
        elif book.opens_from and book.opens_from not in dirs:
            findings.append(
                Finding(
                    "error",
                    "broken-handoff",
                    f"book '{book.dir}' opens_from '{book.opens_from}', "
                    "which is not a book in the series",
                )
            )
    return findings
