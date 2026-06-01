"""Tests for the storyboard (visual-tier) export."""

from __future__ import annotations

import json

from bookkit.bible import BibleConfig, Character
from bookkit.config import BookConfig, ChapterEntry
from bookkit.storyboard import plan_storyboard, write_storyboard


def _make_book(tmp_path, chapters):
    entries = []
    for fname, body in chapters:
        (tmp_path / fname).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / fname).write_text(body, encoding="utf-8")
        entries.append(ChapterEntry(file=fname, title=""))
    return BookConfig(title="Visual Test", chapters=entries)


def test_storyboard_one_panel_per_paragraph(tmp_path):
    config = _make_book(
        tmp_path,
        [("chapters/01.md", "# Open\n\nFirst beat happens.\n\nSecond beat happens.")],
    )
    plan = plan_storyboard(config, tmp_path)
    ch = plan.chapters[0]
    assert ch.name == "chapter_01"
    assert ch.title == "Open"
    assert len(ch.panels) == 2
    assert ch.panels[0].scene == "First beat happens."
    assert ch.panels[0].id == "p01_001"


def test_storyboard_long_paragraph_splits_into_panels(tmp_path):
    para = "Sentence one is here. Sentence two is here. Sentence three is here."
    config = _make_book(tmp_path, [("chapters/01.md", para)])
    plan = plan_storyboard(config, tmp_path, max_panel_chars=30)
    assert len(plan.chapters[0].panels) >= 2
    assert all(len(p.scene) <= 30 for p in plan.chapters[0].panels if not p.dialogue)


def test_storyboard_attributes_dialogue_and_characters(tmp_path):
    config = _make_book(tmp_path, [("chapters/01.md", '"Run," said Mara. Dieter froze.')])
    bible = BibleConfig(
        characters=[
            Character(name="Mara", description="Tall, cropped hair, scarred jaw."),
            Character(name="Dieter", description="Stocky, bearded."),
        ]
    )
    plan = plan_storyboard(config, tmp_path, bible=bible)
    panel = plan.chapters[0].panels[0]
    assert {"character": "MARA", "text": "Run,"} in panel.dialogue
    # Both characters present (Mara via dialogue, Dieter via name mention).
    assert panel.characters == ["DIETER", "MARA"]
    # Art notes carry the canonical descriptions for present characters.
    assert any("Tall, cropped hair" in n for n in panel.art_notes)
    assert any("Stocky, bearded" in n for n in panel.art_notes)


def test_storyboard_no_bible_has_no_art_notes(tmp_path):
    config = _make_book(tmp_path, [("chapters/01.md", "Just narration here.")])
    plan = plan_storyboard(config, tmp_path)
    panel = plan.chapters[0].panels[0]
    assert panel.art_notes == []
    assert panel.dialogue == []
    assert panel.characters == []


def test_write_storyboard_layout_and_unicode(tmp_path):
    config = _make_book(tmp_path, [("chapters/01.md", "Vera miró la montaña nevada.")])
    bible = BibleConfig(characters=[Character(name="Vera", description="Arquitecta.")])
    plan = plan_storyboard(config, tmp_path, bible=bible)
    dest = tmp_path / "out"
    written = write_storyboard(plan, dest)

    assert written == ["chapter_01/storyboard.json"]
    doc = json.loads((dest / "chapter_01" / "storyboard.json").read_text(encoding="utf-8"))
    assert set(doc) == {"title", "panels"}
    assert doc["panels"][0]["id"] == "p01_001"
    assert "montaña" in doc["panels"][0]["scene"]
    raw = (dest / "chapter_01" / "storyboard.json").read_text(encoding="utf-8")
    assert "\\u" not in raw  # accents stay human-readable


def test_write_storyboard_preserves_existing_unless_forced(tmp_path):
    config = _make_book(tmp_path, [("chapters/01.md", "Panel text.")])
    plan = plan_storyboard(config, tmp_path)
    dest = tmp_path / "out"
    write_storyboard(plan, dest)

    path = dest / "chapter_01" / "storyboard.json"
    path.write_text("hand-tuned", encoding="utf-8")
    assert write_storyboard(plan, dest) == []  # preserved
    assert path.read_text(encoding="utf-8") == "hand-tuned"
    assert write_storyboard(plan, dest, force=True) == ["chapter_01/storyboard.json"]
    assert path.read_text(encoding="utf-8") != "hand-tuned"
