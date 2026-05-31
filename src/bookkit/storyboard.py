"""Turn a book's chapters into a storyboard — the canonical *visual* script.

This is the visual-tier sibling of :mod:`bookkit.audiobook`. Where the audiobook
bridge emits a podcastkit project (audio), this emits a storyboard: an ordered
list of *panels* per chapter, each with a scene description, the dialogue spoken
in it, and the characters present — with art-direction notes pulled straight
from the bible so a character looks the same in every panel they appear in.

It is deliberately renderer-agnostic. A comic generator (panel → drawn image)
and a video/animatic tool (panel → shot) consume the *same* storyboard.json, the
same way the EPUB and PDF renderers consume the same chapters: one canonical
source, many rendered media. bookkit produces the script; rendering pixels is a
separate tier, exactly as rendering audio is podcastkit's job and not bookkit's.

Generation is deterministic — one panel per paragraph (long paragraphs split to
a target size) — so it is fully unit-testable without any image model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ._dialogue import Matcher, attribute_paragraph
from ._manuscript import load_chapter, split_title
from .audiobook import chunk_text, markdown_to_speech, slugify
from .bible import BibleConfig
from .config import BookConfig


@dataclass
class Panel:
    id: str
    scene: str  # narration / description for the panel
    dialogue: list[dict] = field(default_factory=list)  # [{character, text}]
    characters: list[str] = field(default_factory=list)  # present, for art consistency
    art_notes: list[str] = field(default_factory=list)  # appearance cues from the bible


@dataclass
class StoryboardChapter:
    name: str  # output sub-directory, e.g. "chapter_01"
    title: str
    panels: list[Panel] = field(default_factory=list)


@dataclass
class Storyboard:
    project: str
    chapters: list[StoryboardChapter]

    @property
    def panel_count(self) -> int:
        return sum(len(c.panels) for c in self.chapters)


def _art_notes(characters: list[str], bible: BibleConfig | None) -> list[str]:
    """Appearance/voice cues for the named characters, drawn from the bible.

    The art department gets the same canonical description the prose was written
    against, so the character a reader pictures and an artist draws are one.
    """
    if not bible:
        return []
    notes: list[str] = []
    for canon in characters:
        character = bible.character(canon)
        if character is None:
            continue
        detail = character.description or character.voice
        if detail:
            notes.append(f"{character.name}: {detail}")
    return notes


def plan_storyboard(
    config: BookConfig,
    book_dir,
    *,
    bible: BibleConfig | None = None,
    max_panel_chars: int = 320,
    project_name: str | None = None,
) -> Storyboard:
    """Turn a loaded book into a :class:`Storyboard` (no files written).

    Each chapter paragraph becomes a panel (paragraphs over ``max_panel_chars``
    split into several, on sentence boundaries). Dialogue is attributed with the
    same engine the full-cast audiobook uses; characters present are detected by
    name so the panel carries their canonical look.
    """
    matcher = Matcher(bible)
    chapters: list[StoryboardChapter] = []

    for index, entry in enumerate(config.chapters, start=1):
        chapter = load_chapter(entry, book_dir, index)
        raw = (book_dir / entry.file).read_text(encoding="utf-8")
        _, body = split_title(raw)
        speech = markdown_to_speech(body)

        panels: list[Panel] = []
        for paragraph in speech.split("\n\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            for piece in chunk_text(paragraph, max_panel_chars):
                segments = attribute_paragraph(piece, matcher, "NARRATOR")
                scene = " ".join(t for spk, t in segments if spk == "NARRATOR").strip()
                dialogue = [
                    {"character": spk, "text": t} for spk, t in segments if spk != "NARRATOR"
                ]
                present = sorted(matcher.find_all(piece) | {d["character"] for d in dialogue})
                panel_no = len(panels) + 1
                panels.append(
                    Panel(
                        id=f"p{index:02d}_{panel_no:03d}",
                        scene=scene,
                        dialogue=dialogue,
                        characters=present,
                        art_notes=_art_notes(present, bible),
                    )
                )

        chapters.append(
            StoryboardChapter(name=f"chapter_{index:02d}", title=chapter.title, panels=panels)
        )

    project = project_name or f"{slugify(config.title)}-storyboard"
    return Storyboard(project=project, chapters=chapters)


def write_storyboard(plan: Storyboard, dest: Path, *, force: bool = False) -> list[str]:
    """Write one ``storyboard.json`` per chapter under ``dest``.

    Layout mirrors the audiobook project (one sub-dir per chapter)::

        <dest>/
          chapter_01/storyboard.json   # {title, panels: [{id, scene, dialogue, ...}]}
          chapter_02/storyboard.json

    Existing files are preserved unless ``force`` is set. Returns the relative
    paths written.
    """
    dest.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for chapter in plan.chapters:
        ch_dir = dest / chapter.name
        ch_dir.mkdir(parents=True, exist_ok=True)
        path = ch_dir / "storyboard.json"
        if not (force or not path.exists()):
            continue
        doc = {
            "title": chapter.title or chapter.name,
            "panels": [
                {
                    "id": panel.id,
                    "scene": panel.scene,
                    "dialogue": panel.dialogue,
                    "characters": panel.characters,
                    "art_notes": panel.art_notes,
                }
                for panel in chapter.panels
            ],
        }
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(f"{chapter.name}/storyboard.json")
    return written
