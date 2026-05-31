from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.fixture
def tmp_book(tmp_path: Path) -> Path:
    """A minimal book directory with a valid book.yaml and two Markdown chapters."""
    book = tmp_path / "my-book"
    chapters = book / "chapters"
    chapters.mkdir(parents=True)

    (chapters / "01-intro.md").write_text(
        "# Introduction\n\nThis is the **first** chapter. It has two sentences.\n",
        encoding="utf-8",
    )
    (chapters / "02-method.md").write_text(
        "# First Principles\n\nStart from what you cannot doubt.\n\n> A quote.\n",
        encoding="utf-8",
    )

    config = {
        "title": "Test Book",
        "subtitle": "A Fixture",
        "author": {"name": "A. Author", "bio": "Writes test books."},
        "language": "en",
        "output": "test-book.epub",
        "theme": {"base_font": "serif", "page_size": "6x9", "font_size_pt": 11.0},
        "chapters": [
            {"file": "chapters/01-intro.md", "title": ""},
            {"file": "chapters/02-method.md", "title": ""},
        ],
        "front_matter": ["title_page", "toc"],
        "back_matter": ["about_author"],
    }
    (book / "book.yaml").write_text(yaml.dump(config, allow_unicode=True), encoding="utf-8")
    return book
