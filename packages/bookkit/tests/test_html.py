from __future__ import annotations

from bookkit._html import _copyright_page
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
