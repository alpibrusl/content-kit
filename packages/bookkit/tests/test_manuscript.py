from __future__ import annotations

from pathlib import Path

from bookkit._manuscript import load_chapters, slugify, split_title
from bookkit.config import BookConfig


def test_slugify() -> None:
    assert slugify("First Principles") == "first-principles"
    assert slugify("  Spaces & Symbols! ") == "spaces-symbols"
    assert slugify("") == "chapter"


def test_split_title_extracts_leading_h1() -> None:
    title, body = split_title("# My Title\n\nSome body.\n")
    assert title == "My Title"
    assert body.strip() == "Some body."


def test_split_title_no_heading() -> None:
    title, body = split_title("Just body text, no heading.\n")
    assert title == ""
    assert "Just body" in body


def test_load_chapters_dedupes_slugs(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# Same\n\nOne.\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# Same\n\nTwo.\n", encoding="utf-8")
    cfg = BookConfig(
        title="T",
        chapters=[{"file": "a.md"}, {"file": "b.md"}],
    )
    chapters = load_chapters(cfg, tmp_path)
    assert [c.id for c in chapters] == ["same", "same-2"]
    assert chapters[0].word_count == 1


def test_chapter_title_override(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# Original\n\nBody.\n", encoding="utf-8")
    cfg = BookConfig(title="T", chapters=[{"file": "a.md", "title": "Overridden"}])
    chapters = load_chapters(cfg, tmp_path)
    assert chapters[0].title == "Overridden"
