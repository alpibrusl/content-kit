from __future__ import annotations

from pathlib import Path

from .._html import build_document
from .._manuscript import Chapter
from ..config import BookConfig
from .base import Renderer


class PdfRenderer(Renderer):
    """Render to a print-ready PDF via WeasyPrint (HTML + CSS paged media).

    Requires the ``pdf`` extra: ``pip install 'bookkit[pdf]'``. The same HTML and
    stylesheet that drive the HTML renderer are paginated here using the @page
    rules in the built-in CSS (page size comes from the book's theme).
    """

    extension = "pdf"

    def render(
        self,
        config: BookConfig,
        chapters: list[Chapter],
        book_dir: Path,
        dest: Path,
    ) -> None:
        try:
            from weasyprint import HTML
        except ImportError as exc:
            raise RuntimeError(
                "weasyprint is not installed. Run: pip install 'bookkit[pdf]'"
            ) from exc

        dest.parent.mkdir(parents=True, exist_ok=True)
        document = build_document(config, chapters, book_dir)
        # base_url lets relative asset references (e.g. images) resolve from the book dir.
        HTML(string=document, base_url=str(book_dir)).write_pdf(str(dest))
