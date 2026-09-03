"""Budget-aware assembly of the continuity context fed into chapter generation.

When writing chapter N, the model is given three layers (see docs/continuity.md §3,§6):
canon (the bible, sliced to what matters by N), the running recap of chapters
1…N-1, and optionally the full text of chapter N-1. This module renders those
layers to plain text and locates the per-chapter source/recap files.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .bible import BibleConfig
from .config import BookConfig


def bible_to_prompt_text(bible: BibleConfig, upto_chapter: int | None = None) -> str:
    """Render the canon as compact prompt text.

    Characters (with their established voice and current status), world facts, and
    the timeline up to ``upto_chapter`` are included. Characters that only appear
    after this chapter are dropped to save budget.
    """
    lines: list[str] = []
    if bible.logline:
        lines.append(f"LOGLINE: {bible.logline}")
    if bible.themes:
        lines.append(f"THEMES: {', '.join(bible.themes)}")

    chars = [
        c
        for c in bible.characters
        if upto_chapter is None or c.first_appears is None or c.first_appears <= upto_chapter
    ]
    if chars:
        lines.append("\nCHARACTERS:")
        for c in chars:
            bits = [f"- {c.name}"]
            if c.role:
                bits.append(f"({c.role})")
            if c.status and c.status != "alive":
                bits.append(f"[status: {c.status}]")
            lines.append(" ".join(bits))
            if c.description:
                lines.append(f"    who: {c.description}")
            if c.voice:
                lines.append(f"    voice: {c.voice}")
            if c.arc:
                lines.append(f"    arc: {c.arc}")
            for rel in c.relationships:
                lines.append(f"    relationship: {rel.with_} — {rel.nature}")

    if bible.world:
        lines.append("\nWORLD:")
        lines.extend(f"- {w.fact}" for w in bible.world)

    if bible.timeline:
        lines.append("\nTIMELINE:")
        lines.extend(f"- {t.when}: {t.event}" if t.when else f"- {t.event}" for t in bible.timeline)

    return "\n".join(lines).strip()


def find_chapter_file(book_dir: Path, chapter_num: int) -> Path | None:
    """Locate a chapter's Markdown source, by book.yaml order or NN-* glob."""
    book_yaml = book_dir / "book.yaml"
    if book_yaml.exists():
        raw = yaml.safe_load(book_yaml.read_text(encoding="utf-8")) or {}
        config = BookConfig.model_validate(raw)
        if 1 <= chapter_num <= len(config.chapters):
            candidate = book_dir / config.chapters[chapter_num - 1].file
            if candidate.exists():
                return candidate
    matches = sorted((book_dir / "chapters").glob(f"{chapter_num:02d}-*.md"))
    return matches[0] if matches else None


def assemble_recap(book_dir: Path, chapter_num: int) -> str:
    """Concatenate stored recaps for chapters 1…chapter_num-1."""
    recaps_dir = book_dir / "recaps"
    if not recaps_dir.exists():
        return ""
    parts: list[str] = []
    for n in range(1, chapter_num):
        path = recaps_dir / f"{n:02d}.md"
        if path.exists():
            parts.append(f"[Chapter {n}] {path.read_text(encoding='utf-8').strip()}")
    return "\n\n".join(parts)


def prev_chapter_text(book_dir: Path, chapter_num: int, *, max_chars: int = 12000) -> str:
    """Full text of the immediately preceding chapter, truncated to a char budget."""
    if chapter_num <= 1:
        return ""
    path = find_chapter_file(book_dir, chapter_num - 1)
    if not path:
        return ""
    text = path.read_text(encoding="utf-8").strip()
    return text[:max_chars]


def read_chapters(book_dir: Path, config: BookConfig | None = None) -> dict[int, str]:
    """Every chapter's Markdown source, keyed by chapter number.

    Numbering follows the filename's leading digits when it has them, because
    that is the number the prose itself refers to ("see Chapter 7") and the
    number a ledger's ``defined_in`` means. Falling back to position in
    ``book.yaml`` keeps this working for books that don't number their files.
    A book with no ``book.yaml`` is read straight from ``chapters/``.
    """
    book_yaml = book_dir / "book.yaml"
    if config is None and book_yaml.exists():
        raw = yaml.safe_load(book_yaml.read_text(encoding="utf-8")) or {}
        config = BookConfig.model_validate(raw)
    if config is not None:
        entries = [c.file for c in config.chapters]
    else:
        found = sorted((book_dir / "chapters").glob("*.md"))
        entries = [str(p.relative_to(book_dir)) for p in found]

    out: dict[int, str] = {}
    for index, entry in enumerate(entries, start=1):
        path = book_dir / entry
        if not path.exists():
            continue
        match = re.match(r"^(\d+)-", path.name)
        number = int(match.group(1)) if match else index
        out[number] = path.read_text(encoding="utf-8")
    return out
