"""How much of one book is already in another.

A series that reuses a method across volumes will reuse some prose with it, and
some of that is right: the argument for computing rather than guessing does not
change because the domain did. What is not right is a chapter a reader
recognises — same shape, same sentences, the domain nouns swapped — because the
second reading then feels like a find-and-replace of the first, and the book
that could have earned its own version never does.

That is measurable, so it does not have to be something a reader notices on the
second volume. This module reports, per chapter, how much of it has a near-twin
somewhere in a sibling book.

The comparison is deliberately literal — no synonym table, no stemming. A
sentence rewritten to say the same thing differently is exactly what this
module wants to *stop* reporting, so the moment an author does that work the
number falls on its own.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path

from ._context import read_chapters
from .continuity import Finding, strip_noise

# Sentence pairs at or above this ratio count as the same sentence. Calibrated
# against the two books in this series that share a method: genuinely reused
# chapters land at 28-57% shared, independently written ones at 0-3%. The gap
# is wide enough that the exact number matters little.
DEFAULT_CUTOFF = 0.85
DEFAULT_THRESHOLD = 0.25

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[a-z']+")
# Below this word count a sentence is too short to be evidence of anything:
# "That is the point." recurs in unrelated prose all the time.
_MIN_WORDS = 7


@dataclass
class ChapterOverlap:
    chapter: int
    other_chapter: int
    shared: int
    total: int

    @property
    def ratio(self) -> float:
        return self.shared / self.total if self.total else 0.0


def sentences(markdown: str) -> list[str]:
    """The prose sentences of a chapter, long enough to be distinctive."""
    text = " ".join(strip_noise(markdown).split())
    found = []
    for raw in _SENTENCE_SPLIT_RE.split(text):
        sentence = raw.strip()
        if len(sentence.split()) >= _MIN_WORDS:
            found.append(sentence)
    return found


def _tokens(sentence: str) -> frozenset[str]:
    return frozenset(_WORD_RE.findall(sentence.lower()))


def _similar(a: str, b: str, cutoff: float) -> bool:
    """Whether two sentences are the same sentence, near enough.

    The token-overlap test first is purely for speed: comparing every sentence
    of every chapter against every sentence of every other is quadratic twice
    over, and most pairs are not remotely alike.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    if len(ta & tb) / max(len(ta), len(tb)) < cutoff - 0.25:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= cutoff


def compare(
    book: dict[int, str],
    other: dict[int, str],
    *,
    cutoff: float = DEFAULT_CUTOFF,
) -> list[ChapterOverlap]:
    """For each chapter, its closest counterpart in ``other`` and how much they share.

    Every chapter is compared against every chapter of the sibling rather than
    against the one with the same number, so a chapter that has moved is still
    recognised.
    """
    other_sentences = {n: sentences(t) for n, t in other.items()}
    results: list[ChapterOverlap] = []
    for number in sorted(book):
        mine = sentences(book[number])
        if not mine:
            continue
        best = ChapterOverlap(number, 0, 0, len(mine))
        for other_number, theirs in other_sentences.items():
            if not theirs:
                continue
            shared = sum(1 for s in mine if any(_similar(s, t, cutoff) for t in theirs))
            if shared > best.shared:
                best = ChapterOverlap(number, other_number, shared, len(mine))
        results.append(best)
    return results


def check_duplication(
    book_dir: Path,
    other_dir: Path,
    *,
    cutoff: float = DEFAULT_CUTOFF,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[Finding]:
    """Report chapters that share too much of their prose with a sibling book."""
    book = read_chapters(book_dir)
    other = read_chapters(other_dir)
    findings: list[Finding] = []
    for overlap in compare(book, other, cutoff=cutoff):
        if overlap.ratio < threshold:
            continue
        findings.append(
            Finding(
                "warning",
                "duplicate-chapter",
                f"{overlap.ratio:.0%} of chapter {overlap.chapter} "
                f"({overlap.shared} of {overlap.total} sentences) also appears in "
                f"{other_dir.name} chapter {overlap.other_chapter} — keep the argument "
                "parallel, but let each book earn its own examples and failure cases",
                overlap.chapter,
            )
        )
    return findings
