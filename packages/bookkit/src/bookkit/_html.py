"""Shared HTML + CSS construction for every renderer.

The HTML renderer emits this directly, the PDF renderer feeds it to WeasyPrint,
and the EPUB renderer reuses the per-chapter fragments and stylesheet. Keeping it
in one place means a book looks the same whatever it is rendered to.
"""

from __future__ import annotations

import base64
import functools
import html
import mimetypes
import re
from pathlib import Path

from content_kit_core.provenance import build_stamp

from ._labels import labels_for
from ._manuscript import Chapter, render_markdown, slugify, split_title
from .config import BookConfig, MatterEntry

_FONT_STACKS = {
    "serif": '"EB Garamond", Georgia, "Iowan Old Style", "Times New Roman", serif',
    "sans": '"Helvetica Neue", Arial, system-ui, sans-serif',
    "mono": '"SF Mono", "DejaVu Sans Mono", Consolas, monospace',
}

_FONTS_DIR = Path(__file__).parent / "assets" / "fonts"
_EMBEDDED_FONT_FILES = {
    "normal": "EBGaramond12-Regular.otf",
    "bold": "EBGaramond12-Bold.otf",
    "italic": "EBGaramond12-Italic.otf",
}


@functools.lru_cache(maxsize=1)
def _embedded_font_faces() -> str:
    """``@font-face`` rules embedding EB Garamond (OFL-1.1) as data URIs.

    Bundling a real book typeface — rather than trusting the reader's system
    Georgia/Times fallback — is what makes the PDF and EPUB look the same
    everywhere instead of drifting with whatever fonts happen to be
    installed. See ``assets/fonts/OFL-EBGaramond.txt`` for the licence.
    """
    faces = []
    styles = {"normal": "normal", "bold": "normal", "italic": "italic"}
    weights = {"normal": "400", "bold": "700", "italic": "400"}
    for key, filename in _EMBEDDED_FONT_FILES.items():
        path = _FONTS_DIR / filename
        if not path.exists():
            return ""
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        faces.append(
            "@font-face {\n"
            '  font-family: "EB Garamond";\n'
            f"  font-style: {styles[key]};\n"
            f"  font-weight: {weights[key]};\n"
            f'  src: url("data:font/otf;base64,{data}") format("opentype");\n'
            "}"
        )
    return "\n".join(faces)


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
    font_faces = _embedded_font_faces() if theme.base_font == "serif" else ""
    return f"""\
{font_faces}
@page {{
  size: {page};
  margin: 22mm 16mm 20mm;
  /* Margin boxes inherit from the page context, not from body, so without
     this the running header and every page number render in the reader's
     default font while the text is set in the embedded book face. */
  font-family: {font};
  @top-center {{
    /* `first-except` yields the empty string on the page where the string is
       set, which is the chapter's own opening page -- where the title is
       already printed two inches down and a running head repeating it is the
       thing book typography drops. Continuation pages carry it normally.
       Named page groups cannot do this: WeasyPrint reads `:first` as the
       first page of the document, not of the group, so `@page chapter:first`
       suppresses only the first chapter's opener however the names alternate. */
    content: string(chaptertitle, first-except);
    font-size: 8pt;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #9a9a9a;
  }}
  @bottom-center {{ content: counter(page); font-size: 9pt; color: #666; }}
}}
@page :first {{ @top-center {{ content: none; }} }}
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
h1.chapter-title {{ font-size: 1.8em; margin: 0 0 1.5rem; string-set: chaptertitle content(); }}
p.chapter-number {{
  margin: 0 0 0.5rem;
  font-size: 0.8em;
  font-weight: 600;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #9a9a9a;
}}
section.chapter {{ page-break-before: always; padding-top: 1rem; }}
section.front-matter {{ page-break-after: always; text-align: center; page: frontmatter; }}
@page frontmatter {{ @top-center {{ content: none; }} }}
section.cover {{ page: cover; margin: -2rem -1rem 0; padding: 0; line-height: 0; }}
section.cover img {{ width: 100%; display: block; }}
@page cover {{ margin: 0; @top-center {{ content: none; }} @bottom-center {{ content: none; }} }}
.title-page h1 {{ font-size: 2.6em; margin-top: 30vh; }}
.title-page .subtitle {{ font-size: 1.3em; color: #444; font-style: italic; }}
.title-page .author {{ margin-top: 2rem; font-size: 1.1em; }}
.copyright {{ font-size: 0.9em; color: #444; }}
.copyright p {{ text-align: center; }}
.copyright .license {{ margin-top: 1.5rem; }}
.copyright .notice {{ font-size: 0.85em; }}
/* The build stamp is reference matter, not reading matter: findable when
   somebody needs to rebuild this exact artifact, and quiet otherwise. */
.copyright .build-stamp {{
  margin-top: 2rem;
  font-family: {_FONT_STACKS["mono"]};
  font-size: 0.68em;
  color: #8a8a8a;
  word-break: break-word;
}}
nav.toc {{ text-align: left; }}
nav.toc ol {{ list-style: none; padding: 0; }}
nav.toc ol ol {{ padding-left: 1.2em; }}
nav.toc li {{ margin: 0.5rem 0; }}
nav.toc li.toc-part {{
  margin: 1.6rem 0 0.6rem;
  font-variant-caps: small-caps;
  letter-spacing: 0.06em;
  color: #555;
}}
nav.toc li.toc-part:first-child {{ margin-top: 0; }}
nav.toc a {{ text-decoration: none; color: #1a1a1a; }}
nav.toc a::after {{
  content: leader(".") target-counter(attr(href), page);
  color: #999;
}}
ul {{ list-style: none; margin: 0 0 0.8rem; padding-left: 1.4em; }}
ul li {{ margin: 0 0 0.3rem; }}
ul li::before {{ content: "\\00B7\\00A0\\00A0"; font-weight: 700; }}
p {{ margin: 0 0 0.8rem; text-align: justify; }}
blockquote {{ border-left: 3px solid #ccc; margin: 1rem 0; padding-left: 1rem; color: #444; }}
code {{ font-family: {_FONT_STACKS["mono"]}; font-size: 0.9em; }}
pre {{ background: #f5f5f5; padding: 1rem; overflow-x: auto; }}
"""


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


_CHAPTER_NUM_RE = re.compile(r"^(Chapter\s+\d+)\s*[—–-]\s*(.+)$", re.IGNORECASE)


def chapter_section(chapter: Chapter) -> str:
    """Standalone HTML <section> for one chapter (heading + body).

    A title of the form "Chapter N — Title" (the convention a book.yaml
    override uses to put visible numbers in the rendered book) splits into a
    small numeral label above the heading proper, so the number reads as
    typographic structure rather than just more words in the title.
    """
    match = _CHAPTER_NUM_RE.match(chapter.title)
    if match:
        number, rest = match.groups()
        heading = (
            f'<p class="chapter-number">{_esc(number)}</p>\n'
            f'<h1 class="chapter-title">{_esc(rest)}</h1>'
        )
    else:
        heading = f'<h1 class="chapter-title">{_esc(chapter.title)}</h1>'
    return f'<section class="chapter" id="{chapter.id}">\n{heading}\n{chapter.html}\n</section>'


def _title_page(config: BookConfig) -> str:
    parts = [f"<h1>{_esc(config.title)}</h1>"]
    if config.subtitle:
        parts.append(f'<p class="subtitle">{_esc(config.subtitle)}</p>')
    if config.author.name:
        parts.append(f'<p class="author">{_esc(config.author.name)}</p>')
    return '<section class="front-matter title-page">\n' + "\n".join(parts) + "\n</section>"


def _copyright_page(config: BookConfig, book_dir: Path | None = None) -> str:
    """The copyright page, which is also where the build stamp belongs.

    A rendered book is an artifact, and Chapter 1 of *Prompt to Production*
    insists an artifact should be reproducible from its source and its recorded
    build inputs. Recording them nowhere and asserting it anyway would be the
    engine failing the book's own standard, on the book's own copyright page.
    """
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

    if book_dir is not None:
        stamp = build_stamp(book_dir, ["bookkit"])
        labels = labels_for(config.language)
        lines.append(f'<p class="build-stamp">{_esc(labels["built_from"])} {_esc(stamp)}</p>')

    return '<section class="front-matter copyright">\n' + "\n".join(lines) + "\n</section>"


def _toc(config: BookConfig, chapters: list[Chapter]) -> str:
    """The table of contents, grouped by part when the book declares any.

    A book with no parts renders exactly as before: one flat ordered list.
    """
    heading = labels_for(config.language)["contents"]
    parts = [entry.part for entry in config.chapters]

    lines: list[str] = []
    open_list = False
    padded = parts + [""] * len(chapters)
    for chapter, part in zip(chapters, padded, strict=False):
        if part:
            if open_list:
                lines.append("</ol>")
            lines.append(f'<li class="toc-part">{_esc(part)}</li>')
            lines.append("<ol>")
            open_list = True
        lines.append(f'<li><a href="#{chapter.id}">{_esc(chapter.title)}</a></li>')
    if open_list:
        lines.append("</ol>")

    items = "\n".join(lines)
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


def front_matter_sections(
    config: BookConfig, chapters: list[Chapter], book_dir: Path | None = None
) -> list[str]:
    builders = {
        "title_page": lambda: _title_page(config),
        "copyright": lambda: _copyright_page(config, book_dir),
        "toc": lambda: _toc(config, chapters),
    }
    out = []
    for entry in config.front_matter:
        if isinstance(entry, MatterEntry):
            if book_dir is not None:
                out.append(_matter_file_section(entry, book_dir)[2])
        elif entry in builders:
            out.append(builders[entry]())
    return out


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


def iter_front_matter(
    config: BookConfig, book_dir: Path | None = None
) -> list[tuple[str, str, str]]:
    """Front matter as discrete ``(slug, title, html)`` documents.

    For renderers that paginate into separate files (EPUB). The ``toc`` section
    is omitted on purpose: those renderers build their own navigation, so a
    second hand-rolled table of contents would only duplicate it.
    """
    labels = labels_for(config.language)
    builders = {
        "title_page": ("title-page", config.title or labels["title"], lambda: _title_page(config)),
        "copyright": (
            "copyright",
            labels["copyright"],
            lambda: _copyright_page(config, book_dir),
        ),
    }
    docs = []
    for entry in config.front_matter:
        if isinstance(entry, MatterEntry):
            if book_dir is not None:
                docs.append(_matter_file_section(entry, book_dir))
        elif entry in builders:
            slug, title, build = builders[entry]
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
        *front_matter_sections(config, chapters, book_dir),
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
