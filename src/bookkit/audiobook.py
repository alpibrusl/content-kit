"""Turn a book's Markdown chapters into a podcastkit-compatible project.

This is the bridge between the two halves of the content pipeline: bookkit owns
the *canonical source* (Markdown chapters + ``book.yaml`` + ``bible.yaml``), and
podcastkit owns *audio rendering* (``script.json`` + ``episode.yaml`` → MP3 via
TTS + ffmpeg). The two CLIs are deliberately decoupled siblings — they share
conventions but never import each other — so the link between them is a plain
artifact: this module reads a book and writes a podcastkit project that
``podcastkit generate`` / ``podcastkit assemble`` can render unchanged.

Two design choices keep this honest and reproducible:

* **Prose, not HTML.** Narration text is Markdown stripped to plain spoken
  prose (headings, emphasis, links, lists flattened), then chunked into
  TTS-sized lines on sentence boundaries — never mid-sentence.
* **The bible *is* the voice cast.** A character defined once in ``bible.yaml``
  (name + ``voice`` description) becomes an entry in the episode's ``voices``
  map, so the same canon that keeps a character consistent in the book seeds
  how they sound in the audiobook. v1 narrates everything as one NARRATOR voice;
  the cast is wired in (with placeholder voice ids) for the author to extend
  into a full-cast reading without re-deriving who the characters are.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ._manuscript import load_chapter, split_title
from .bible import BibleConfig
from .config import BookConfig

# Default per-line silence (seconds), matching podcastkit's own default.
_PRE_SILENCE = 0.5
# A longer beat before the first line of each chapter, so chapters breathe.
_CHAPTER_GAP = 1.0
# Sentence boundary: end punctuation (incl. Spanish/ellipsis) + whitespace.
_SENTENCE_RE = re.compile(r"(?<=[.!?…])[\"'”’)\]]*\s+")

# --- Markdown → spoken prose -------------------------------------------------

_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_BLOCKQUOTE_RE = re.compile(r"^\s{0,3}>\s?", re.MULTILINE)
_LIST_MARKER_RE = re.compile(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+", re.MULTILINE)
_HR_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$", re.MULTILINE)
_EMPHASIS_RE = re.compile(r"(\*{1,3}|_{1,3}|`+)(.+?)\1", re.DOTALL)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")


def markdown_to_speech(md: str) -> str:
    """Flatten Markdown prose into plain spoken text, preserving paragraphs.

    The goal is what a narrator would *say*, not what a reader would *see*:
    formatting markers are removed, link text is kept (URLs dropped), images and
    code fences are discarded, and paragraph breaks are preserved as blank lines
    so the chunker can group sentences sensibly.
    """
    text = _CODE_FENCE_RE.sub("", md)
    text = _IMAGE_RE.sub("", text)
    text = _LINK_RE.sub(r"\1", text)
    text = _HR_RE.sub("", text)
    text = _HEADING_RE.sub("", text)
    text = _BLOCKQUOTE_RE.sub("", text)
    text = _LIST_MARKER_RE.sub("", text)
    # Collapse emphasis/inline-code markers, keeping the wrapped text. Repeat to
    # handle nested or adjacent markers (e.g. **_bold italic_**).
    for _ in range(3):
        new = _EMPHASIS_RE.sub(r"\2", text)
        if new == text:
            break
        text = new
    text = html.unescape(text)
    # Normalize whitespace inside paragraphs; keep blank lines as separators.
    paragraphs = [
        " ".join(block.split()) for block in _MULTI_BLANK_RE.sub("\n\n", text).split("\n\n")
    ]
    return "\n\n".join(p for p in paragraphs if p)


def chunk_text(text: str, max_chars: int) -> list[str]:
    """Split spoken text into TTS-sized chunks on sentence boundaries.

    Paragraphs are never merged. Within a paragraph, whole sentences are packed
    up to ``max_chars``; a single sentence longer than ``max_chars`` is split on
    clause boundaries (then hard-split as a last resort) so no chunk is ever
    truncated mid-word by a TTS backend's input limit.
    """
    chunks: list[str] = []
    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        sentences = _split_sentences(paragraph)
        buf = ""
        for sentence in sentences:
            for piece in _fit(sentence, max_chars):
                if not buf:
                    buf = piece
                elif len(buf) + 1 + len(piece) <= max_chars:
                    buf = f"{buf} {piece}"
                else:
                    chunks.append(buf)
                    buf = piece
        if buf:
            chunks.append(buf)
    return chunks


def _split_sentences(paragraph: str) -> list[str]:
    parts = _SENTENCE_RE.split(paragraph)
    return [p.strip() for p in parts if p.strip()]


def _fit(sentence: str, max_chars: int) -> list[str]:
    """Break a single over-long sentence into <= max_chars pieces."""
    if len(sentence) <= max_chars:
        return [sentence]
    pieces: list[str] = []
    buf = ""
    # Prefer clause boundaries (comma, semicolon, colon, em dash).
    for clause in re.split(r"(?<=[,;:—–])\s+", sentence):
        if not buf:
            buf = clause
        elif len(buf) + 1 + len(clause) <= max_chars:
            buf = f"{buf} {clause}"
        else:
            pieces.append(buf)
            buf = clause
    if buf:
        pieces.append(buf)
    # Last resort: hard-split any clause still too long.
    out: list[str] = []
    for piece in pieces:
        while len(piece) > max_chars:
            out.append(piece[:max_chars])
            piece = piece[max_chars:]
        if piece:
            out.append(piece)
    return out


# --- Plan model --------------------------------------------------------------


@dataclass
class Line:
    id: str
    character: str
    text: str


@dataclass
class Episode:
    """One podcastkit episode (one rendered MP3) — here, one book chapter."""

    name: str  # output sub-directory name, e.g. "chapter_01"
    title: str
    output: str  # final MP3 filename
    script: list[Line] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return sum(len(line.text) for line in self.script)


@dataclass
class AudiobookPlan:
    """Everything needed to write a podcastkit project for one book."""

    project: str  # top-level project directory name
    episodes: list[Episode]
    voices: dict[str, dict]  # character -> VoiceConfig dict, shared across episodes
    narrator: str  # the narration character name

    @property
    def line_count(self) -> int:
        return sum(len(ep.script) for ep in self.episodes)

    @property
    def char_count(self) -> int:
        return sum(ep.char_count for ep in self.episodes)


# --- Book → plan -------------------------------------------------------------


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "audiobook"


def _voice_cast(
    backend: str, voice_id: str, narrator: str, bible: BibleConfig | None
) -> dict[str, dict]:
    """Build the episode ``voices`` map: the narrator plus the bible's cast.

    The narrator gets the chosen backend/voice. Each character from the bible is
    seeded with the same backend and a ``REPLACE_ME`` voice id so a full-cast
    reading is one edit away — and so the audiobook's cast is, by construction,
    the same canon the book was written against.
    """
    voices: dict[str, dict] = {narrator: {"backend": backend, "voice_id": voice_id}}
    if bible is not None:
        for character in bible.characters:
            name = character.name.strip().upper()
            if not name or name == narrator:
                continue
            entry: dict = {"backend": backend, "voice_id": "REPLACE_ME"}
            if character.voice:
                # Carry the canonical voice description across so the author casts
                # against the same note the prose was written to.
                entry["note"] = character.voice
            voices.setdefault(name, entry)
    return voices


def plan_audiobook(
    config: BookConfig,
    book_dir,
    *,
    bible: BibleConfig | None = None,
    backend: str = "kokoro",
    voice_id: str = "bm_george",
    narrator: str = "NARRATOR",
    max_chars: int = 600,
    project_name: str | None = None,
) -> AudiobookPlan:
    """Turn a loaded book into an :class:`AudiobookPlan` (no files written).

    One episode is produced per chapter. Chapter prose is flattened to speech,
    chunked into TTS-sized narration lines, and timed with a slightly longer gap
    before each chapter's first line. Pure and deterministic, so it is unit-
    testable without touching TTS or the filesystem beyond reading chapters.
    """
    narrator = narrator.strip().upper() or "NARRATOR"
    prefix = "narr" if narrator == "NARRATOR" else slugify(narrator).replace("-", "")[:4] or "narr"
    voices = _voice_cast(backend, voice_id, narrator, bible)

    episodes: list[Episode] = []
    for index, entry in enumerate(config.chapters, start=1):
        chapter = load_chapter(entry, book_dir, index)
        raw = (book_dir / entry.file).read_text(encoding="utf-8")
        _, body = split_title(raw)
        speech = markdown_to_speech(body)
        chunks = chunk_text(speech, max_chars)

        script: list[Line] = []
        timeline: list[dict] = []
        for n, chunk in enumerate(chunks, start=1):
            line_id = f"{prefix}_{index:02d}_{n:04d}"
            script.append(Line(id=line_id, character=narrator, text=chunk))
            pre = _CHAPTER_GAP if n == 1 else _PRE_SILENCE
            timeline.append({"id": line_id, "pre_silence": pre})

        episodes.append(
            Episode(
                name=f"chapter_{index:02d}",
                title=chapter.title,
                output=f"chapter_{index:02d}.mp3",
                script=script,
                timeline=timeline,
            )
        )

    project = project_name or f"{slugify(config.title)}-audiobook"
    return AudiobookPlan(project=project, episodes=episodes, voices=voices, narrator=narrator)


# --- Plan → podcastkit project -----------------------------------------------


def write_project(plan: AudiobookPlan, dest: Path, *, force: bool = False) -> list[str]:
    """Write a podcastkit-compatible project tree under ``dest``.

    Layout (one episode dir per chapter), matching what ``podcastkit generate``
    and ``podcastkit assemble`` expect::

        <dest>/
          chapter_01/
            script.json      # [{id, character, text}, ...]
            episode.yaml     # {title, output, voices, timeline}
          chapter_02/ ...

    Existing ``script.json`` / ``episode.yaml`` files are preserved unless
    ``force`` is set, so re-running over a project an author has hand-tuned (e.g.
    cast a real voice) never clobbers their work. Returns the relative paths
    written or skipped, for reporting.
    """
    dest.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for episode in plan.episodes:
        ep_dir = dest / episode.name
        ep_dir.mkdir(parents=True, exist_ok=True)

        script_path = ep_dir / "script.json"
        if force or not script_path.exists():
            payload = [
                {"id": line.id, "character": line.character, "text": line.text}
                for line in episode.script
            ]
            script_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            written.append(f"{episode.name}/script.json")

        episode_path = ep_dir / "episode.yaml"
        if force or not episode_path.exists():
            doc = {
                "title": episode.title or episode.name,
                "output": episode.output,
                "voices": plan.voices,
                "timeline": episode.timeline,
            }
            episode_path.write_text(
                yaml.dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8"
            )
            written.append(f"{episode.name}/episode.yaml")
    return written
