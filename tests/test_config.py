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
