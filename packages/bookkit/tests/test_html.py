from __future__ import annotations

import yaml

from bookkit._html import _copyright_page, default_css, iter_front_matter
from bookkit.config import BookConfig


def _cfg(**kwargs: object) -> BookConfig:
    base: dict = {"title": "T", "chapters": [{"file": "a.md"}]}
    base.update(kwargs)
    return BookConfig.model_validate(base)


def test_copyright_page_legacy_defaults() -> None:
    # With no copyright block, the page keeps the legacy shape: title + © author.
    html = _copyright_page(_cfg(author={"name": "Jane Roe"}, isbn="123"))
    assert "&copy; Jane Roe" in html
    assert "ISBN 123" in html
    assert "license" not in html


def test_copyright_page_renders_license_and_notice() -> None:
    html = _copyright_page(
        _cfg(
            author={"name": "Pen Name"},
            copyright={
                "year": "2026",
                "license": "CC BY-NC-ND 4.0",
                "license_url": "https://creativecommons.org/licenses/by-nc-nd/4.0/",
                "notice": ["Compartir con atribución.", "Hecho con asistencia de IA."],
            },
        )
    )
    assert "&copy; 2026 Pen Name" in html
    url = "https://creativecommons.org/licenses/by-nc-nd/4.0/"
    assert f'<a href="{url}">CC BY-NC-ND 4.0</a>' in html
    assert '<p class="notice">Compartir con atribución.</p>' in html
    assert '<p class="notice">Hecho con asistencia de IA.</p>' in html


def test_copyright_holder_overrides_author() -> None:
    html = _copyright_page(_cfg(author={"name": "Pen"}, copyright={"holder": "Legal Name"}))
    assert "&copy; Legal Name" in html
    assert "Pen" not in html


# --- localized labels, cover page, stylesheet_mode, file-based back matter ---

from bookkit._html import build_document, resolve_css  # noqa: E402
from bookkit._labels import labels_for  # noqa: E402
from bookkit._manuscript import load_chapters  # noqa: E402


def test_labels_fall_back_to_english() -> None:
    assert labels_for("xx")["contents"] == "Contents"
    assert labels_for("")["contents"] == "Contents"
    assert labels_for("es-ES")["contents"] == "Índice"


def _doc(book_dir, **overrides):
    import yaml

    cfg_data = yaml.safe_load((book_dir / "book.yaml").read_text(encoding="utf-8"))
    cfg_data.update(overrides)
    config = BookConfig.model_validate(cfg_data)
    chapters = load_chapters(config, book_dir)
    return build_document(config, chapters, book_dir)


def test_generated_labels_follow_book_language(tmp_book) -> None:
    html = _doc(tmp_book, language="es", front_matter=["toc"], back_matter=["about_author"])
    assert "<h1>Índice</h1>" in html
    assert "<h1>Sobre el autor</h1>" in html
    assert "Contents" not in html
    assert "About the Author" not in html


def test_cover_is_inlined_in_document(tmp_book) -> None:
    # A 1x1 PNG; the cover section must embed it as a data URI (self-contained).
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c626001000000ffff03000006000557bfabd40000000049454e44ae426082"
    )
    (tmp_book / "cover.png").write_bytes(png)
    html = _doc(tmp_book, cover="cover.png")
    assert '<section class="front-matter cover">' in html
    assert "data:image/png;base64," in html


def test_missing_cover_is_skipped(tmp_book) -> None:
    html = _doc(tmp_book, cover="nope.png")
    assert 'class="front-matter cover"' not in html


def test_stylesheet_mode_replace_and_extend(tmp_book) -> None:
    (tmp_book / "custom.css").write_text("body { color: red; }", encoding="utf-8")
    replaced = resolve_css(
        BookConfig.model_validate(
            {"title": "T", "chapters": [{"file": "a.md"}], "theme": {"stylesheet": "custom.css"}}
        ),
        tmp_book,
    )
    assert replaced.strip() == "body { color: red; }"
    extended = resolve_css(
        BookConfig.model_validate(
            {
                "title": "T",
                "chapters": [{"file": "a.md"}],
                "theme": {"stylesheet": "custom.css", "stylesheet_mode": "extend"},
            }
        ),
        tmp_book,
    )
    assert "@page" in extended  # built-in base kept
    assert extended.rstrip().endswith("body { color: red; }")  # custom wins last


def test_back_matter_file_entry_renders_as_section(tmp_book) -> None:
    (tmp_book / "COLOPHON.md").write_text("# Colofón\n\nHecho con *bookkit*.\n", encoding="utf-8")
    html = _doc(tmp_book, back_matter=[{"file": "COLOPHON.md", "title": ""}, "about_author"])
    assert '<h1 class="chapter-title">Colofón</h1>' in html
    assert "<em>bookkit</em>" in html
    # order respected: file entry before about_author
    assert html.index("Colofón") < html.index("About the Author")


def test_a_front_matter_file_renders_before_the_chapters(tmp_book) -> None:
    """The point of the feature: it has to land ahead of chapter 1, not after."""
    (tmp_book / "PREFACE.md").write_text(
        "# How to read this\n\nFour books, one argument.\n", encoding="utf-8"
    )
    raw = yaml.safe_load((tmp_book / "book.yaml").read_text())
    raw["front_matter"] = [
        "title_page",
        {"file": "PREFACE.md", "title": "How to read this"},
        "toc",
    ]
    (tmp_book / "book.yaml").write_text(yaml.dump(raw), encoding="utf-8")
    config = BookConfig.model_validate(raw)
    chapters = load_chapters(config, tmp_book)

    html = build_document(config, chapters, tmp_book)
    assert "Four books, one argument." in html
    # Chapter 1's own body, not the bare word "first" -- the stylesheet has an
    # `@page :first` rule, and matching that would pass no matter where the
    # front matter landed.
    assert html.index("Four books, one argument.") < html.index("It has two sentences.")


def test_front_matter_files_are_separate_epub_documents(tmp_book) -> None:
    (tmp_book / "PREFACE.md").write_text("# Preface\n\nRead this first.\n", encoding="utf-8")
    raw = yaml.safe_load((tmp_book / "book.yaml").read_text())
    raw["front_matter"] = ["title_page", {"file": "PREFACE.md", "title": "Preface"}]
    config = BookConfig.model_validate(raw)

    docs = iter_front_matter(config, tmp_book)
    titles = [t for _, t, _ in docs]
    assert "Preface" in titles
    assert any("Read this first." in html for _, _, html in docs)


def test_toc_groups_by_part_when_the_book_declares_them(tmp_book) -> None:
    raw = yaml.safe_load((tmp_book / "book.yaml").read_text())
    raw["chapters"][0]["part"] = "Part I — The Ground"
    raw["chapters"][1]["part"] = "Part II — Keeping It"
    config = BookConfig.model_validate(raw)
    chapters = load_chapters(config, tmp_book)

    html = build_document(config, chapters, tmp_book)
    assert "Part I — The Ground" in html
    assert "Part II — Keeping It" in html
    assert html.index("Part I — The Ground") < html.index("Part II — Keeping It")
    assert html.count('class="toc-part"') == 2


def test_a_flat_book_renders_exactly_as_before(tmp_book) -> None:
    """No parts declared: one ordered list, no part markers at all."""
    config = BookConfig.model_validate(yaml.safe_load((tmp_book / "book.yaml").read_text()))
    html = build_document(config, load_chapters(config, tmp_book), tmp_book)
    # The class attribute, not the bare string -- the stylesheet always carries
    # a rule for it, and that says nothing about what the body rendered.
    assert 'class="toc-part"' not in html


def test_a_part_groups_every_chapter_until_the_next_one(tmp_book) -> None:
    """The name sits on the chapter that opens the part, not on all of them."""
    raw = yaml.safe_load((tmp_book / "book.yaml").read_text())
    raw["chapters"][0]["part"] = "Part I"
    config = BookConfig.model_validate(raw)
    html = build_document(config, load_chapters(config, tmp_book), tmp_book)
    assert html.count('class="toc-part"') == 1
    assert "First Principles" in html


def test_the_page_margin_boxes_use_the_same_face_as_the_body(tmp_book) -> None:
    """Margin boxes inherit from the page context, not from body.

    Without an explicit declaration the running header and every page number
    render in the reader's default font while the text is set in the embedded
    book face -- a mismatch on every page of the book.
    """
    config = BookConfig.model_validate(yaml.safe_load((tmp_book / "book.yaml").read_text()))
    css = default_css(config)

    page_block = css[css.index("@page {") : css.index("@page :first")]
    body_block = css[css.index("body {") : css.index("h1, h2, h3")]
    assert "font-family" in page_block
    stack = page_block.split("font-family:")[1].split(";")[0].strip()
    assert stack == body_block.split("font-family:")[1].split(";")[0].strip()


def test_the_running_head_is_suppressed_on_a_chapter_opening_page(tmp_book) -> None:
    """`string(..., first-except)`, not a bare `string(...)`.

    A chapter's opening page already prints the title two inches down, and a
    running head repeating it is the thing book typography drops. Named page
    groups cannot express this in WeasyPrint -- it reads `:first` as the first
    page of the document rather than of the group -- so this one keyword is
    what the behaviour rests on.
    """
    config = BookConfig.model_validate(yaml.safe_load((tmp_book / "book.yaml").read_text()))
    css = default_css(config)

    top_center = css[css.index("@top-center") : css.index("@bottom-center")]
    assert "string(chaptertitle, first-except)" in top_center


def test_the_copyright_page_records_what_built_the_book(tmp_book) -> None:
    """A rendered book is an artifact, and Chapter 1 of Prompt to Production
    insists an artifact should be reproducible from its source and its recorded
    build inputs. Recording them nowhere would be the engine failing the book's
    own standard, on the book's own copyright page."""
    raw = yaml.safe_load((tmp_book / "book.yaml").read_text())
    raw["front_matter"] = ["copyright"]
    config = BookConfig.model_validate(raw)

    html = build_document(config, load_chapters(config, tmp_book), tmp_book)
    assert 'class="build-stamp"' in html
    assert "Built from source " in html
    assert "bookkit" in html


def test_the_build_stamp_speaks_the_book_s_language(tmp_book) -> None:
    raw = yaml.safe_load((tmp_book / "book.yaml").read_text())
    raw["front_matter"] = ["copyright"]
    raw["language"] = "es"
    config = BookConfig.model_validate(raw)

    html = build_document(config, load_chapters(config, tmp_book), tmp_book)
    assert "Construido desde source " in html
    assert "Built from" not in html
