from __future__ import annotations

import pytest
from pydantic import ValidationError

from bookkit.config import BookConfig


def test_minimal_config_defaults() -> None:
    cfg = BookConfig(title="T", chapters=[{"file": "chapters/01.md"}])
    assert cfg.language == "en"
    assert cfg.theme.base_font == "serif"
    assert cfg.front_matter == ["title_page", "toc"]
    assert cfg.author.name == ""


def test_title_is_required() -> None:
    with pytest.raises(ValidationError):
        BookConfig(chapters=[])


def test_invalid_page_size_rejected() -> None:
    with pytest.raises(ValidationError):
        BookConfig(title="T", chapters=[], theme={"page_size": "tabloid"})


def test_front_matter_accepts_a_file_entry() -> None:
    """A preface or series map has to be able to open the book.

    Only back matter could carry a file, which stranded material a reader needs
    *before* chapter 1 at the end of the book.
    """
    config = BookConfig.model_validate(
        {
            "title": "T",
            "chapters": [{"file": "chapters/01.md"}],
            "front_matter": [
                "title_page",
                {"file": "ABOUT-THE-SERIES.md", "title": "The Series"},
                "toc",
            ],
        }
    )
    assert config.front_matter[0] == "title_page"
    assert config.front_matter[1].file == "ABOUT-THE-SERIES.md"
    assert config.front_matter[2] == "toc"


def test_front_matter_still_defaults_without_files() -> None:
    config = BookConfig.model_validate({"title": "T", "chapters": [{"file": "c.md"}]})
    assert config.front_matter == ["title_page", "toc"]
