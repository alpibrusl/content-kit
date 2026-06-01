from __future__ import annotations

from pathlib import Path

import yaml

from bookkit._context import (
    assemble_recap,
    bible_to_prompt_text,
    find_chapter_file,
    prev_chapter_text,
)
from bookkit.bible import BibleConfig
from bookkit.prompts import build_chapter_prompts

BIBLE = BibleConfig.model_validate(
    {
        "logline": "An auditor vs. an AI.",
        "themes": ["control"],
        "characters": [
            {"name": "MARA", "role": "protagonist", "voice": "Clipped.", "first_appears": 1},
            {"name": "TOMAS", "status": "departed", "first_appears": 1},
            {"name": "LATE", "role": "twist", "first_appears": 5},
        ],
        "world": [{"fact": "The Engine never sleeps."}],
        "beats": [{"chapter": 1, "summary": "The audit begins."}],
    }
)


def test_bible_text_includes_voice_and_status() -> None:
    text = bible_to_prompt_text(BIBLE, upto_chapter=1)
    assert "MARA" in text
    assert "voice: Clipped." in text
    assert "status: departed" in text  # non-default status surfaced
    assert "The Engine never sleeps." in text


def test_bible_text_drops_characters_not_yet_introduced() -> None:
    text = bible_to_prompt_text(BIBLE, upto_chapter=1)
    assert "LATE" not in text
    assert "LATE" in bible_to_prompt_text(BIBLE, upto_chapter=5)


def test_find_chapter_file_via_book_yaml(tmp_path: Path) -> None:
    (tmp_path / "chapters").mkdir()
    (tmp_path / "chapters" / "01-intro.md").write_text("# Intro\n", encoding="utf-8")
    config = {
        "title": "T",
        "chapters": [{"file": "chapters/01-intro.md"}],
    }
    (tmp_path / "book.yaml").write_text(yaml.dump(config), encoding="utf-8")
    found = find_chapter_file(tmp_path, 1)
    assert found is not None and found.name == "01-intro.md"


def test_find_chapter_file_via_glob(tmp_path: Path) -> None:
    (tmp_path / "chapters").mkdir()
    (tmp_path / "chapters" / "03-mid.md").write_text("# Mid\n", encoding="utf-8")
    found = find_chapter_file(tmp_path, 3)
    assert found is not None and found.name == "03-mid.md"


def test_assemble_recap_concatenates_prior(tmp_path: Path) -> None:
    recaps = tmp_path / "recaps"
    recaps.mkdir()
    (recaps / "01.md").write_text("Mara starts the audit.", encoding="utf-8")
    (recaps / "02.md").write_text("Tomas leaves.", encoding="utf-8")
    text = assemble_recap(tmp_path, 3)
    assert "[Chapter 1] Mara starts the audit." in text
    assert "[Chapter 2] Tomas leaves." in text
    # recap for chapter 1 has no prior chapters
    assert assemble_recap(tmp_path, 1) == ""


def test_prev_chapter_text(tmp_path: Path) -> None:
    (tmp_path / "chapters").mkdir()
    (tmp_path / "chapters" / "01-a.md").write_text("# A\n\nBody of one.", encoding="utf-8")
    assert "Body of one." in prev_chapter_text(tmp_path, 2)
    assert prev_chapter_text(tmp_path, 1) == ""  # no chapter 0


def test_chapter_prompt_includes_context_layers() -> None:
    _, user = build_chapter_prompts(
        "OUTLINE",
        2,
        "what happens",
        canon="CANON HERE",
        recap="STORY HERE",
        prev_chapter="PREV HERE",
    )
    assert "CANON HERE" in user
    assert "STORY HERE" in user
    assert "PREV HERE" in user


def test_chapter_prompt_omits_empty_layers() -> None:
    _, user = build_chapter_prompts("OUTLINE", 1, "x")
    assert "Canon (do not contradict)" not in user
    assert "Story so far" not in user
