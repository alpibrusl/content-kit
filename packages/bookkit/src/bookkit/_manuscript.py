"""Parse Markdown chapter sources into rendered chapters.

A book's canonical source is a set of Markdown files plus a ``book.yaml``. This
module turns those files into ``Chapter`` objects (title + rendered HTML + word
count) that every renderer consumes. It is the book-world equivalent of
podcastkit's script parsing: source text in, a normalized structure out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import BookConfig, ChapterEntry

_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")
_WORD_RE = re.compile(r"\b\w+\b")


@dataclass
class Chapter:
    id: str  # slug, used for filenames and in-document anchors (e.g. "first-principles")
    title: str
    html: str  # rendered body HTML (without the chapter <h1>, which renderers add)
    word_count: int


def slugify(text: str) -> str:
    """Turn a chapter title into a stable, filesystem- and URL-safe slug."""
    slug = _SLUG_STRIP_RE.sub("-", text.lower()).strip("-")
    return slug or "chapter"


def split_title(markdown: str) -> tuple[str, str]:
    """Return ``(title, body)`` for a chapter.

    If the source begins with a leading ``# Heading`` it becomes the title and is
    removed from the body (renderers re-add it). Otherwise the title is empty and
    the caller falls back to the configured or positional title.
    """
    match = _H1_RE.search(markdown)
    if match and markdown[: match.start()].strip() == "":
        title = match.group(1).strip()
        body = markdown[: match.start()] + markdown[match.end() :]
        return title, body.lstrip("\n")
    return "", markdown


def render_markdown(body: str) -> str:
    """Render Markdown body text to an HTML fragment."""
    import markdown as md

    return md.markdown(
        body,
        extensions=["extra", "smarty", "sane_lists"],
        output_format="html5",
    )


def count_words(text: str) -> int:
    return len(_WORD_RE.findall(text))


def load_chapter(entry: ChapterEntry, book_dir: Path, index: int) -> Chapter:
    """Read and render a single chapter from its Markdown source."""
    path = book_dir / entry.file
    raw = path.read_text(encoding="utf-8")
    parsed_title, body = split_title(raw)
    title = entry.title or parsed_title or f"Chapter {index}"
    return Chapter(
        id=slugify(title),
        title=title,
        html=render_markdown(body),
        word_count=count_words(body),
    )


def load_chapters(config: BookConfig, book_dir: Path) -> list[Chapter]:
    """Read and render every chapter listed in the book config, in order.

    Slugs are de-duplicated so two chapters that share a title still produce
    distinct anchors and EPUB filenames.
    """
    chapters: list[Chapter] = []
    seen: dict[str, int] = {}
    for i, entry in enumerate(config.chapters, start=1):
        chapter = load_chapter(entry, book_dir, i)
        if chapter.id in seen:
            seen[chapter.id] += 1
            chapter.id = f"{chapter.id}-{seen[chapter.id]}"
        else:
            seen[chapter.id] = 1
        chapters.append(chapter)
    return chapters
