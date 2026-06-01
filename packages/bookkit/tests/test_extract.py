from __future__ import annotations

from bookkit._extract import split_prose_and_yaml


def test_extracts_yaml_fence() -> None:
    text = "# Outline\n\nSome prose.\n\n```yaml\ntitle: T\nbeats: []\n```\n"
    prose, block = split_prose_and_yaml(text)
    assert "Some prose." in prose
    assert "```" not in prose
    assert block == "title: T\nbeats: []"


def test_falls_back_to_bare_fence() -> None:
    text = "Prose here.\n\n```\ntitle: T\n```"
    prose, block = split_prose_and_yaml(text)
    assert block == "title: T"
    assert prose == "Prose here."


def test_no_block_returns_none() -> None:
    prose, block = split_prose_and_yaml("Just prose, no canon.")
    assert block is None
    assert prose == "Just prose, no canon."
