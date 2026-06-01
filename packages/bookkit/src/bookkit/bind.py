"""Bind parsed chapters into a single book artifact.

This is the book-world counterpart of podcastkit's ``assemble``: it takes the
canonical source (``book.yaml`` + Markdown chapters), renders it through the
selected backend, and reports build metrics (word count, chapters, size).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._manuscript import load_chapters
from .config import BookConfig
from .renderers import get_renderer


def output_path(config: BookConfig, book_dir: Path, fmt: str) -> Path:
    """Where the rendered artifact is written: build/<stem>.<fmt>."""
    stem = Path(config.output).stem or "book"
    return book_dir / "build" / f"{stem}.{fmt}"


def bind(config: BookConfig, book_dir: Path, fmt: str) -> dict[str, Any]:
    """Render the book and return build metrics."""
    chapters = load_chapters(config, book_dir)
    renderer = get_renderer(fmt)
    dest = output_path(config, book_dir, fmt)
    renderer.render(config, chapters, book_dir, dest)

    words = sum(c.word_count for c in chapters)
    size_bytes = dest.stat().st_size if dest.exists() else 0
    return {
        "output": str(dest),
        "format": fmt,
        "chapters": len(chapters),
        "words": words,
        # ~300 words per printed page is a standard trade estimate.
        "est_pages": round(words / 300) if words else 0,
        "size_mb": round(size_bytes / (1024 * 1024), 3),
    }
