from __future__ import annotations

from pathlib import Path

from .._html import build_document
from .._manuscript import Chapter
from ..config import BookConfig
from .base import Renderer


class HtmlRenderer(Renderer):
    """Render to a single self-contained HTML file.

    This is the built-in, dependency-free renderer — the book-world analogue of
    Kokoro: always available, no API key, good enough to ship. It is also what the
    test suite exercises so the core pipeline is verifiable without heavy extras.
    """

    extension = "html"

    def render(
        self,
        config: BookConfig,
        chapters: list[Chapter],
        book_dir: Path,
        dest: Path,
    ) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(build_document(config, chapters, book_dir), encoding="utf-8")
