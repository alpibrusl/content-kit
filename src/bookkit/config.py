from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

# The output format a book is rendered to. "html" is the built-in, dependency-free
# renderer (always available); "epub" and "pdf" require optional extras.
RenderFormat = Literal["epub", "pdf", "html"]


class Author(BaseModel):
    name: str = ""
    bio: str = ""  # appears in the optional "about_author" back-matter section


class Theme(BaseModel):
    """Presentation settings shared by every renderer.

    A theme is to a book what a voice cast is to an episode: it does not change
    the words, only how they are rendered.
    """

    stylesheet: str = ""  # path to a custom CSS file, or "" to use the built-in default
    base_font: Literal["serif", "sans", "mono"] = "serif"
    page_size: Literal["6x9", "5x8", "a4", "letter"] = "6x9"  # PDF page geometry
    font_size_pt: float = 11.0


class Copyright(BaseModel):
    """Rights and licence details for the optional "copyright" front-matter page.

    All wording lives here, in the book's own config, so the page stays
    language-agnostic: the engine renders the structure, the book supplies the
    words. Every field is optional; an empty block reproduces the legacy page
    (title, "© author", ISBN).
    """

    holder: str = ""  # rights holder; falls back to author.name when empty
    year: str = ""  # e.g. "2026"
    license: str = ""  # short label, e.g. "CC BY-NC-ND 4.0" or "Todos los derechos reservados"
    license_url: str = ""  # canonical URL for the licence; linked when present
    notice: list[str] = []  # extra paragraphs rendered verbatim (terms, AI disclosure, ...)


class ChapterEntry(BaseModel):
    file: str  # path to the chapter's Markdown source, relative to the book directory
    title: str = ""  # overrides the chapter's leading "# Heading" when set


class BookConfig(BaseModel):
    title: str
    subtitle: str = ""
    author: Author = Author()
    language: str = "en"
    output: str = "book.epub"  # final artifact filename; extension swapped per --format
    cover: str = ""  # path to a cover image (PNG/JPG), relative to the book directory
    isbn: str = ""
    copyright: Copyright = Copyright()  # rights/licence shown on the "copyright" page
    series: str = ""  # optional path to a series.yaml (relative to the book dir)
    theme: Theme = Theme()
    chapters: list[ChapterEntry]  # ordered, like an episode timeline
    front_matter: list[Literal["title_page", "copyright", "toc"]] = ["title_page", "toc"]
    back_matter: list[Literal["about_author"]] = []
