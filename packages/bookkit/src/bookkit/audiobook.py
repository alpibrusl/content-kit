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

from content_kit_core.bridge import validate_episode, validate_script

from ._dialogue import attribute
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
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# An inline diagram is visual apparatus, exactly like a code listing: dropped
# whole, rather than narrated. Without this a listener gets "div style margin
# one point six rem, svg viewBox zero zero six eighty one twenty, xmlns http
# colon slash slash www dot w3 dot org..." in the middle of a sentence.
_SVG_BLOCK_RE = re.compile(r"<svg\b.*?</svg>", re.DOTALL | re.IGNORECASE)
# Anything still carrying tags keeps its text and loses the markup, so a
# caption or a hand-written <em> still reaches the narrator.
_HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_BLOCKQUOTE_RE = re.compile(r"^\s{0,3}>\s?", re.MULTILINE)
_LIST_MARKER_RE = re.compile(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+", re.MULTILINE)
_HR_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$", re.MULTILINE)
_EMPHASIS_RE = re.compile(r"(\*{1,3}|_{1,3}|`+)(.+?)\1", re.DOTALL)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")
# A Markdown table row, and the |---|---| rule that separates head from body.
_TABLE_ROW_RE = re.compile(r"^\s{0,3}\|.*\|\s*$")
_TABLE_RULE_RE = re.compile(r"^\s{0,3}\|(?:\s*:?-+:?\s*\|)+\s*$")


def _table_to_speech(text: str) -> str:
    """Turn Markdown table rows into sentences a narrator can actually read.

    A table is a visual arrangement, but unlike a diagram its cells carry the
    content itself -- a checklist of questions, a rule and its severity -- so
    dropping it would lose the substance rather than the packaging. Each row
    becomes its cells in order, comma-separated; the head/body rule carries no
    words and is dropped. Without this the narrator reads the pipes.
    """
    out: list[str] = []
    for line in text.split("\n"):
        if _TABLE_RULE_RE.match(line):
            continue
        if _TABLE_ROW_RE.match(line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            cells = [c for c in cells if c]
            if not cells:
                continue
            row = ", ".join(cells)
            out.append(row if row.endswith((".", "?", "!")) else row + ".")
            continue
        out.append(line)
    return "\n".join(out)


def markdown_to_speech(md: str) -> str:
    """Flatten Markdown prose into plain spoken text, preserving paragraphs.

    The goal is what a narrator would *say*, not what a reader would *see*:
    formatting markers are removed, link text is kept (URLs dropped), images,
    code fences and inline diagrams are discarded, and paragraph breaks are
    preserved as blank lines so the chunker can group sentences sensibly.
    """
    text = _CODE_FENCE_RE.sub("", md)
    text = _HTML_COMMENT_RE.sub("", text)
    text = _SVG_BLOCK_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    text = _table_to_speech(text)
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

    @property
    def cast_line_count(self) -> int:
        """Lines attributed to a character other than the narrator."""
        return sum(
            1 for ep in self.episodes for line in ep.script if line.character != self.narrator
        )


# --- Book → plan -------------------------------------------------------------


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "audiobook"


def _line_prefix(character: str) -> str:
    """A short, stable id prefix for a character's script lines."""
    name = character.strip().upper()
    if name == "NARRATOR":
        return "narr"
    return slugify(name).replace("-", "")[:4] or "narr"


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
    cast: bool = False,
) -> AudiobookPlan:
    """Turn a loaded book into an :class:`AudiobookPlan` (no files written).

    One episode is produced per chapter. Chapter prose is flattened to speech,
    chunked into TTS-sized lines, and timed with a slightly longer gap before
    each chapter's first line. With ``cast=False`` every line is the narrator
    (a classic single-reader audiobook). With ``cast=True`` quoted/dash-led
    dialogue is attributed to bible characters when an attribution cue names one,
    falling back to the narrator otherwise. Pure and deterministic, so it is
    unit-testable without touching TTS or the filesystem beyond reading chapters.
    """
    narrator = narrator.strip().upper() or "NARRATOR"
    voices = _voice_cast(backend, voice_id, narrator, bible)
    prefixes = {name: _line_prefix(name) for name in voices}
    prefixes.setdefault(narrator, _line_prefix(narrator))

    episodes: list[Episode] = []
    for index, entry in enumerate(config.chapters, start=1):
        chapter = load_chapter(entry, book_dir, index)
        raw = (book_dir / entry.file).read_text(encoding="utf-8")
        _, body = split_title(raw)
        speech = markdown_to_speech(body)

        # (speaker, text) segments: one narrator segment per paragraph in the
        # single-voice case, or attributed dialogue when casting.
        if cast:
            segments = attribute(speech, bible, narrator)
        else:
            segments = [(narrator, para) for para in speech.split("\n\n") if para.strip()]

        # Chunk each segment to TTS size while preserving its speaker.
        spoken: list[tuple[str, str]] = []
        for speaker, seg_text in segments:
            for piece in chunk_text(seg_text, max_chars):
                spoken.append((speaker, piece))

        script: list[Line] = []
        timeline: list[dict] = []
        counters: dict[str, int] = {}
        for n, (speaker, piece) in enumerate(spoken, start=1):
            prefix = prefixes.get(speaker) or _line_prefix(speaker)
            counters[prefix] = counters.get(prefix, 0) + 1
            line_id = f"{prefix}_{index:02d}_{counters[prefix]:04d}"
            script.append(Line(id=line_id, character=speaker, text=piece))
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


def _write_if_changed(path: Path, text: str, *, force: bool = False) -> bool:
    """Write ``text`` to ``path`` unless it is already exactly that. Returns
    whether anything was written.

    Used for the files derived from the manuscript, where comparing content
    rather than merely testing for existence is what keeps ``bookkit audiobook``
    honest after an edit: skipping a file that is already there means a
    corrected chapter regenerates to nothing, silently, and the stale script is
    then rendered as though it were current — the same failure the voice-line
    manifest exists to prevent, one stage earlier in the pipeline. Untouched
    files are still left alone, so the command stays cheap and does not churn
    timestamps for chapters nobody edited.
    """
    if not force and path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


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

        payload = [
            {"id": line.id, "character": line.character, "text": line.text}
            for line in episode.script
        ]
        # Validate against the shared audio-bridge contract *before* writing, so
        # any drift between what bookkit emits and what podcastkit can render
        # fails here — in this producer's own tests — not later at the consumer.
        validate_script(payload)
        script_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if _write_if_changed(ep_dir / "script.json", script_text, force=force):
            written.append(f"{episode.name}/script.json")

        doc = {
            "title": episode.title or episode.name,
            "output": episode.output,
            "voices": plan.voices,
            "timeline": episode.timeline,
        }
        validate_episode(doc)  # same contract the renderer loads — see above
        # episode.yaml carries two things with opposite requirements. `voices` is
        # the cast sheet an author hand-tunes and must survive regeneration.
        # `timeline` is derived from the script and must follow it: preserving
        # the whole file meant that deleting a paragraph left its id in the
        # timeline, so `assemble` went on splicing in audio for a line the
        # manuscript no longer had -- a chapter that narrated prose its own book
        # had cut, with nothing anywhere reporting it.
        episode_path = ep_dir / "episode.yaml"
        if force or not episode_path.exists():
            episode_path.write_text(
                yaml.dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8"
            )
            written.append(f"{episode.name}/episode.yaml")
        else:
            existing = yaml.safe_load(episode_path.read_text(encoding="utf-8")) or {}
            merged = dict(existing)
            merged["timeline"] = doc["timeline"]
            # A character the manuscript introduced since the last run needs a
            # voice; one the author has already cast keeps theirs.
            cast = dict(doc["voices"])
            cast.update(existing.get("voices") or {})
            merged["voices"] = cast
            if merged != existing:
                validate_episode(merged)
                episode_path.write_text(
                    yaml.dump(merged, allow_unicode=True, sort_keys=False), encoding="utf-8"
                )
                written.append(f"{episode.name}/episode.yaml")
    return written
