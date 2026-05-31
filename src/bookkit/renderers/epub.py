from __future__ import annotations

from pathlib import Path

from .._html import chapter_section, resolve_css
from .._manuscript import Chapter
from ..config import BookConfig
from .base import Renderer


class EpubRenderer(Renderer):
    """Render to a reflowable EPUB via ebooklib.

    Requires the ``epub`` extra: ``pip install 'bookkit[epub]'``. Each chapter
    becomes its own XHTML item with a spine entry and a navigation (TOC) link, so
    e-readers get real chapter navigation rather than one long document.
    """

    extension = "epub"

    def render(
        self,
        config: BookConfig,
        chapters: list[Chapter],
        book_dir: Path,
        dest: Path,
    ) -> None:
        try:
            from ebooklib import epub
        except ImportError as exc:
            raise RuntimeError(
                "ebooklib is not installed. Run: pip install 'bookkit[epub]'"
            ) from exc

        dest.parent.mkdir(parents=True, exist_ok=True)

        book = epub.EpubBook()
        book.set_identifier(config.isbn or config.title)
        book.set_title(config.title)
        book.set_language(config.language)
        if config.author.name:
            book.add_author(config.author.name)

        if config.cover:
            cover_path = book_dir / config.cover
            if cover_path.exists():
                book.set_cover(cover_path.name, cover_path.read_bytes())

        css = epub.EpubItem(
            uid="style",
            file_name="style/book.css",
            media_type="text/css",
            content=resolve_css(config, book_dir),
        )
        book.add_item(css)

        spine: list = ["nav"]
        toc: list = []
        for chapter in chapters:
            item = epub.EpubHtml(
                title=chapter.title,
                file_name=f"{chapter.id}.xhtml",
                lang=config.language,
            )
            item.content = chapter_section(chapter)
            item.add_item(css)
            book.add_item(item)
            spine.append(item)
            toc.append(item)

        book.toc = toc
        book.spine = spine
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        epub.write_epub(str(dest), book)
