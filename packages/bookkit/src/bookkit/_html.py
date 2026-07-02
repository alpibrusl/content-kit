"""Shared HTML + CSS construction for every renderer.

The HTML renderer emits this directly, the PDF renderer feeds it to WeasyPrint,
and the EPUB renderer reuses the per-chapter fragments and stylesheet. Keeping it
in one place means a book looks the same whatever it is rendered to.
"""

from __future__ import annotations

import base64
import html
import mimetypes
from pathlib import Path

from ._labels import labels_for
from ._manuscript import Chapter, render_markdown, slugify, split_title
from .config import BookConfig, MatterEntry

_FONT_STACKS = {
    "serif": 'Georgia, "Iowan Old Style", "Times New Roman", serif',
    "sans": '"Helvetica Neue", Arial, system-ui, sans-serif',
    "mono": '"SF Mono", "DejaVu Sans Mono", Consolas, monospace',
}

_PAGE_SIZES = {
    "6x9": "6in 9in",
    "5x8": "5in 8in",
    "a4": "A4",
    "letter": "letter",
}


def default_css(config: BookConfig) -> str:
    """Built-in stylesheet, parameterized by the book's theme."""
    theme = config.theme
    font = _FONT_STACKS.get(theme.base_font, _FONT_STACKS["serif"])
    page = _PAGE_SIZES.get(theme.page_size, _PAGE_SIZES["6x9"])
    return f"""\
@page {{
  size: {page};
  margin: 18mm 16mm;
  @bottom-center {{ content: counter(page); font-size: 9pt; color: #666; }}
}}
body {{
  font-family: {font};
  font-size: {theme.font_size_pt}pt;
  line-height: 1.5;
  color: #1a1a1a;
  max-width: 34rem;
  margin: 0 auto;
  padding: 2rem 1rem;
}}
h1, h2, h3 {{ line-height: 1.2; font-weight: 600; }}
h1.chapter-title {{ font-size: 1.8em; margin: 0 0 1.5rem; }}
section.chapter {{ page-break-before: always; }}
section.front-matter {{ page-break-after: always; text-align: center; }}
section.cover {{ text-align: center; }}
section.cover img {{ max-width: 100%; max-height: 96vh; }}
.title-page h1 {{ font-size: 2.6em; margin-top: 30vh; }}
.title-page .subtitle {{ font-size: 1.3em; color: #444; font-style: italic; }}
.title-page .author {{ margin-top: 2rem; font-size: 1.1em; }}
.copyright {{ font-size: 0.9em; color: #444; }}
.copyright p {{ text-align: center; }}
.copyright .license {{ margin-top: 1.5rem; }}
.copyright .notice {{ font-size: 0.85em; }}
nav.toc {{ text-align: left; }}
nav.toc ol {{ list-style: none; padding: 0; }}
nav.toc li {{ margin: 0.4rem 0; }}
nav.toc a {{ text-decoration: none; color: #1a1a1a; }}
p {{ margin: 0 0 0.8rem; text-align: justify; }}
blockquote {{ border-left: 3px solid #ccc; margin: 1rem 0; padding-left: 1rem; color: #444; }}
code {{ font-family: {_FONT_STACKS["mono"]}; font-size: 0.9em; }}
pre {{ background: #f5f5f5; padding: 1rem; overflow-x: auto; }}
"""


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def chapter_section(chapter: Chapter) -> str:
    """Standalone HTML <section> for one chapter (heading + body)."""
    return (
        f'<section class="chapter" id="{chapter.id}">\n'
        f'<h1 class="chapter-title">{_esc(chapter.title)}</h1>\n'
        f"{chapter.html}\n"
        "</section>"
    )


def _title_page(config: BookConfig) -> str:
    parts = [f"<h1>{_esc(config.title)}</h1>"]
    if config.subtitle:
        parts.append(f'<p class="subtitle">{_esc(config.subtitle)}</p>')
    if config.author.name:
        parts.append(f'<p class="author">{_esc(config.author.name)}</p>')
    return '<section class="front-matter title-page">\n' + "\n".join(parts) + "\n</section>"


def _copyright_page(config: BookConfig) -> str:
    rights = config.copyright
    holder = rights.holder or config.author.name
    lines = [f"<p>{_esc(config.title)}</p>"]

    notice = "&copy;"
    if rights.year:
        notice += f" {_esc(rights.year)}"
    if holder:
        notice += f" {_esc(holder)}"
    if notice != "&copy;":
        lines.append(f"<p>{notice}</p>")

    if rights.license:
        label = _esc(rights.license)
        if rights.license_url:
            label = f'<a href="{_esc(rights.license_url)}">{label}</a>'
        lines.append(f'<p class="license">{label}</p>')
    for paragraph in rights.notice:
        lines.append(f'<p class="notice">{_esc(paragraph)}</p>')

    if config.isbn:
        lines.append(f"<p>ISBN {_esc(config.isbn)}</p>")
    return '<section class="front-matter copyright">\n' + "\n".join(lines) + "\n</section>"


def _toc(config: BookConfig, chapters: list[Chapter]) -> str:
    heading = labels_for(config.language)["contents"]
    items = "\n".join(f'<li><a href="#{c.id}">{_esc(c.title)}</a></li>' for c in chapters)
    return (
        '<section class="front-matter toc">\n<nav class="toc">\n'
        f"<h1>{_esc(heading)}</h1>\n<ol>\n"
        f"{items}\n</ol>\n</nav>\n</section>"
    )


def _about_author(config: BookConfig) -> str:
    if not (config.author.name or config.author.bio):
        return ""
    heading = labels_for(config.language)["about_author"]
    body = f"<h1>{_esc(heading)}</h1>\n<p>{_esc(config.author.bio)}</p>"
    return f'<section class="chapter about-author">\n{body}\n</section>'


def _cover_section(config: BookConfig, book_dir: Path) -> str:
    """Cover page for the single-document renderers (HTML, PDF).

    The image is inlined as a data URI so the HTML artifact stays
    self-contained and the PDF needs no asset path at render time.
    """
    if not config.cover:
        return ""
    cover_path = book_dir / config.cover
    if not cover_path.exists():
        return ""
    mime = mimetypes.guess_type(cover_path.name)[0] or "image/png"
    data = base64.b64encode(cover_path.read_bytes()).decode("ascii")
    alt = labels_for(config.language)["cover"]
    return (
        '<section class="front-matter cover">\n'
        f'<img src="data:{mime};base64,{data}" alt="{_esc(alt)}">\n'
        "</section>"
    )


def _matter_file_section(entry: MatterEntry, book_dir: Path) -> tuple[str, str, str]:
    """Load a Markdown matter file → ``(slug, title, html section)``."""
    path = book_dir / entry.file
    title, body = split_title(path.read_text(encoding="utf-8"))
    title = entry.title or title or path.stem
    slug = slugify(title) or slugify(path.stem)
    section = (
        f'<section class="chapter matter" id="{slug}">\n'
        f'<h1 class="chapter-title">{_esc(title)}</h1>\n'
        f"{render_markdown(body)}\n"
        "</section>"
    )
    return slug, title, section


def front_matter_sections(config: BookConfig, chapters: list[Chapter]) -> list[str]:
    builders = {
        "title_page": lambda: _title_page(config),
        "copyright": lambda: _copyright_page(config),
        "toc": lambda: _toc(config, chapters),
    }
    return [builders[name]() for name in config.front_matter if name in builders]


def back_matter_sections(config: BookConfig, book_dir: Path) -> list[str]:
    out = []
    for entry in config.back_matter:
        if entry == "about_author":
            section = _about_author(config)
            if section:
                out.append(section)
        elif isinstance(entry, MatterEntry):
            out.append(_matter_file_section(entry, book_dir)[2])
    return out


def iter_front_matter(config: BookConfig) -> list[tuple[str, str, str]]:
    """Front matter as discrete ``(slug, title, html)`` documents.

    For renderers that paginate into separate files (EPUB). The ``toc`` section
    is omitted on purpose: those renderers build their own navigation, so a
    second hand-rolled table of contents would only duplicate it.
    """
    labels = labels_for(config.language)
    builders = {
        "title_page": ("title-page", config.title or labels["title"], lambda: _title_page(config)),
        "copyright": ("copyright", labels["copyright"], lambda: _copyright_page(config)),
    }
    docs = []
    for name in config.front_matter:
        if name in builders:
            slug, title, build = builders[name]
            docs.append((slug, title, build()))
    return docs


def iter_back_matter(config: BookConfig, book_dir: Path) -> list[tuple[str, str, str]]:
    """Back matter as discrete ``(slug, title, html)`` documents (EPUB)."""
    docs = []
    for entry in config.back_matter:
        if entry == "about_author":
            html = _about_author(config)
            if html:
                docs.append(("about-author", labels_for(config.language)["about_author"], html))
        elif isinstance(entry, MatterEntry):
            docs.append(_matter_file_section(entry, book_dir))
    return docs


def resolve_css(config: BookConfig, book_dir: Path) -> str:
    """Return the stylesheet text.

    A custom file replaces the built-in default (``stylesheet_mode: replace``,
    the historical behavior) or is appended after it (``extend``), so a book can
    override a few rules without owning the whole page setup.
    """
    if config.theme.stylesheet:
        css_path = book_dir / config.theme.stylesheet
        if css_path.exists():
            custom = css_path.read_text(encoding="utf-8")
            if config.theme.stylesheet_mode == "extend":
                return default_css(config) + "\n/* --- custom stylesheet (extend) --- */\n" + custom
            return custom
    return default_css(config)


def build_document(config: BookConfig, chapters: list[Chapter], book_dir: Path) -> str:
    """Assemble a complete, standalone HTML document for the whole book."""
    css = resolve_css(config, book_dir)
    cover = _cover_section(config, book_dir)
    body_sections = [
        *([cover] if cover else []),
        *front_matter_sections(config, chapters),
        *(chapter_section(c) for c in chapters),
        *back_matter_sections(config, book_dir),
    ]
    body = "\n".join(body_sections)
    lang = _esc(config.language)
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{lang}">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{_esc(config.title)}</title>\n"
        f"<style>\n{css}\n</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )
