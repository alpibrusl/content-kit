"""Shared HTML + CSS construction for every renderer.

The HTML renderer emits this directly, the PDF renderer feeds it to WeasyPrint,
and the EPUB renderer reuses the per-chapter fragments and stylesheet. Keeping it
in one place means a book looks the same whatever it is rendered to.
"""

from __future__ import annotations

import html
from pathlib import Path

from ._manuscript import Chapter
from .config import BookConfig

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
.title-page h1 {{ font-size: 2.6em; margin-top: 30vh; }}
.title-page .subtitle {{ font-size: 1.3em; color: #444; font-style: italic; }}
.title-page .author {{ margin-top: 2rem; font-size: 1.1em; }}
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
    lines = [f"<p>{_esc(config.title)}</p>"]
    if config.author.name:
        lines.append(f"<p>&copy; {_esc(config.author.name)}</p>")
    if config.isbn:
        lines.append(f"<p>ISBN {_esc(config.isbn)}</p>")
    return '<section class="front-matter copyright">\n' + "\n".join(lines) + "\n</section>"


def _toc(chapters: list[Chapter]) -> str:
    items = "\n".join(f'<li><a href="#{c.id}">{_esc(c.title)}</a></li>' for c in chapters)
    return (
        '<section class="front-matter toc">\n<nav class="toc">\n'
        "<h1>Contents</h1>\n<ol>\n"
        f"{items}\n</ol>\n</nav>\n</section>"
    )


def _about_author(config: BookConfig) -> str:
    if not (config.author.name or config.author.bio):
        return ""
    body = f"<h1>About the Author</h1>\n<p>{_esc(config.author.bio)}</p>"
    return f'<section class="chapter about-author">\n{body}\n</section>'


def front_matter_sections(config: BookConfig, chapters: list[Chapter]) -> list[str]:
    builders = {
        "title_page": lambda: _title_page(config),
        "copyright": lambda: _copyright_page(config),
        "toc": lambda: _toc(chapters),
    }
    return [builders[name]() for name in config.front_matter if name in builders]


def back_matter_sections(config: BookConfig) -> list[str]:
    out = []
    for name in config.back_matter:
        if name == "about_author":
            section = _about_author(config)
            if section:
                out.append(section)
    return out


def resolve_css(config: BookConfig, book_dir: Path) -> str:
    """Return the stylesheet text — a custom file if set, else the built-in default."""
    if config.theme.stylesheet:
        css_path = book_dir / config.theme.stylesheet
        if css_path.exists():
            return css_path.read_text(encoding="utf-8")
    return default_css(config)


def build_document(config: BookConfig, chapters: list[Chapter], book_dir: Path) -> str:
    """Assemble a complete, standalone HTML document for the whole book."""
    css = resolve_css(config, book_dir)
    body_sections = [
        *front_matter_sections(config, chapters),
        *(chapter_section(c) for c in chapters),
        *back_matter_sections(config),
    ]
    body = "\n".join(body_sections)
    lang = _esc(config.language)
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{lang}">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{_esc(config.title)}</title>\n"
        f"<style>\n{css}\n</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )
