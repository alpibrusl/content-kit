"""Tests for the audiobook bridge (bookkit -> podcastkit project)."""

from __future__ import annotations

import json

import yaml

from bookkit.audiobook import (
    AudiobookPlan,
    chunk_text,
    markdown_to_speech,
    plan_audiobook,
    write_project,
)
from bookkit.bible import BibleConfig, Character
from bookkit.config import BookConfig, ChapterEntry

# --- markdown_to_speech ------------------------------------------------------


def test_markdown_to_speech_strips_formatting():
    md = (
        "# A Heading\n\n"
        "This is **bold** and _italic_ and `code` text.\n\n"
        "See [the link](https://example.com) for more.\n"
    )
    out = markdown_to_speech(md)
    assert "#" not in out
    assert "**" not in out and "_" not in out and "`" not in out
    assert "bold" in out and "italic" in out and "code" in out
    # Link text kept, URL dropped.
    assert "the link" in out
    assert "example.com" not in out


def test_markdown_to_speech_drops_images_and_code_fences():
    md = "Intro.\n\n```python\nprint('hi')\n```\n\n![alt](pic.png)\n\nOutro."
    out = markdown_to_speech(md)
    assert "print" not in out
    assert "alt" not in out and "pic.png" not in out
    assert "Intro." in out and "Outro." in out


def test_markdown_to_speech_preserves_paragraphs():
    out = markdown_to_speech("First para.\n\nSecond para.")
    assert out.split("\n\n") == ["First para.", "Second para."]


def test_markdown_to_speech_flattens_lists_and_quotes():
    md = "> quoted line\n\n- one\n- two\n\n1. first\n2. second"
    out = markdown_to_speech(md)
    assert ">" not in out
    assert not any(line.lstrip().startswith(("-", "*", "1.", "2.")) for line in out.splitlines())
    assert "quoted line" in out and "one" in out and "first" in out


# --- chunk_text --------------------------------------------------------------


def test_chunk_text_respects_max_and_sentence_boundaries():
    text = "Sentence one is here. Sentence two is here. Sentence three is here."
    chunks = chunk_text(text, max_chars=30)
    assert chunks  # non-empty
    for c in chunks:
        assert len(c) <= 30
    # No chunk ends mid-word: every chunk is whole sentences (ends with '.').
    assert all(c.endswith(".") for c in chunks)
    # Round-trips the words in order.
    assert " ".join(chunks).split() == text.split()


def test_chunk_text_never_merges_paragraphs():
    chunks = chunk_text("Para one.\n\nPara two.", max_chars=1000)
    assert chunks == ["Para one.", "Para two."]


def test_chunk_text_hard_splits_overlong_sentence():
    long = "word " * 100  # 500 chars, single sentence, no punctuation
    chunks = chunk_text(long.strip() + ".", max_chars=50)
    assert all(len(c) <= 50 for c in chunks)
    # Nothing is lost.
    assert "".join(chunks).replace(" ", "").rstrip(".") == ("word" * 100)


def test_chunk_text_splits_long_sentence_on_clauses():
    text = "First clause here, second clause here, third clause here, fourth clause here."
    chunks = chunk_text(text, max_chars=35)
    assert all(len(c) <= 35 for c in chunks)
    assert " ".join(chunks).split() == text.split()


# --- plan_audiobook ----------------------------------------------------------


def _make_book(tmp_path, chapters):
    """Write chapter files + return a BookConfig pointing at them."""
    (tmp_path / "chapters").mkdir(exist_ok=True)
    entries = []
    for fname, body in chapters:
        (tmp_path / fname).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / fname).write_text(body, encoding="utf-8")
        entries.append(ChapterEntry(file=fname, title=""))
    return BookConfig(title="My Test Book", chapters=entries)


def test_plan_one_episode_per_chapter(tmp_path):
    config = _make_book(
        tmp_path,
        [
            ("chapters/01.md", "# Chapter One\n\nHello there. This is chapter one."),
            ("chapters/02.md", "# Chapter Two\n\nGoodbye now. This is chapter two."),
        ],
    )
    plan = plan_audiobook(config, tmp_path)
    assert len(plan.episodes) == 2
    assert plan.episodes[0].name == "chapter_01"
    assert plan.episodes[0].title == "Chapter One"
    assert plan.episodes[1].output == "chapter_02.mp3"
    # Title heading is not narrated as body text.
    joined = " ".join(line.text for line in plan.episodes[0].script)
    assert "Chapter One" not in joined
    assert "Hello there." in joined


def test_plan_timeline_and_ids_align(tmp_path):
    config = _make_book(tmp_path, [("chapters/01.md", "One. Two. Three.")])
    plan = plan_audiobook(config, tmp_path, max_chars=20)
    ep = plan.episodes[0]
    assert [ln.id for ln in ep.script] == [t["id"] for t in ep.timeline]
    # First line of a chapter gets the longer chapter gap.
    assert ep.timeline[0]["pre_silence"] == 1.0
    assert all(t["pre_silence"] == 0.5 for t in ep.timeline[1:])
    # IDs are unique and chapter-scoped.
    assert len({ln.id for ln in ep.script}) == len(ep.script)
    assert all(ln.id.startswith("narr_01_") for ln in ep.script)


def test_plan_default_narrator_voice(tmp_path):
    config = _make_book(tmp_path, [("chapters/01.md", "Text.")])
    plan = plan_audiobook(config, tmp_path, backend="kokoro", voice_id="bm_george")
    assert plan.voices["NARRATOR"] == {"backend": "kokoro", "voice_id": "bm_george"}
    assert all(line.character == "NARRATOR" for line in plan.episodes[0].script)


def test_plan_bible_cast_becomes_voice_cast(tmp_path):
    config = _make_book(tmp_path, [("chapters/01.md", "Text.")])
    bible = BibleConfig(
        characters=[
            Character(name="Mara", voice="Clipped, precise."),
            Character(name="Dieter", voice="Measured."),
        ]
    )
    plan = plan_audiobook(config, tmp_path, bible=bible)
    # Narrator + both characters, upper-cased.
    assert set(plan.voices) == {"NARRATOR", "MARA", "DIETER"}
    # Canonical voice description carried across for the author to cast against.
    assert plan.voices["MARA"]["note"] == "Clipped, precise."
    assert plan.voices["MARA"]["voice_id"] == "REPLACE_ME"


def test_plan_char_count_sums_text(tmp_path):
    config = _make_book(tmp_path, [("chapters/01.md", "abcde fghij.")])
    plan = plan_audiobook(config, tmp_path)
    assert plan.char_count == len("abcde fghij.")


def test_plan_single_voice_is_all_narrator(tmp_path):
    config = _make_book(tmp_path, [("chapters/01.md", '"Run," said Mara. She bolted away.')])
    bible = BibleConfig(characters=[Character(name="Mara")])
    plan = plan_audiobook(config, tmp_path, bible=bible)  # cast defaults to False
    assert all(line.character == "NARRATOR" for line in plan.episodes[0].script)
    assert plan.cast_line_count == 0


def test_plan_cast_attributes_dialogue(tmp_path):
    config = _make_book(tmp_path, [("chapters/01.md", '"Run," said Mara. She bolted away.')])
    bible = BibleConfig(characters=[Character(name="Mara", voice="Urgent.")])
    plan = plan_audiobook(config, tmp_path, bible=bible, cast=True)
    chars = [line.character for line in plan.episodes[0].script]
    assert "MARA" in chars  # dialogue attributed
    assert "NARRATOR" in chars  # narration retained
    assert plan.cast_line_count >= 1
    # Attributed line ids carry the character's prefix, narration stays "narr".
    mara_lines = [ln for ln in plan.episodes[0].script if ln.character == "MARA"]
    assert all(ln.id.startswith("mara_01_") for ln in mara_lines)


# --- write_project -----------------------------------------------------------


def test_write_project_emits_podcastkit_layout(tmp_path):
    config = _make_book(tmp_path, [("chapters/01.md", "# Intro\n\nOne sentence. Two sentence.")])
    plan = plan_audiobook(config, tmp_path)
    dest = tmp_path / "out"
    written = write_project(plan, dest)

    assert "chapter_01/script.json" in written
    assert "chapter_01/episode.yaml" in written

    script = json.loads((dest / "chapter_01" / "script.json").read_text(encoding="utf-8"))
    assert isinstance(script, list)
    assert script and set(script[0]) == {"id", "character", "text"}

    episode = yaml.safe_load((dest / "chapter_01" / "episode.yaml").read_text(encoding="utf-8"))
    assert set(episode) == {"title", "output", "voices", "timeline"}
    assert episode["output"] == "chapter_01.mp3"
    # script ids and timeline ids match — podcastkit's core invariant.
    assert [s["id"] for s in script] == [t["id"] for t in episode["timeline"]]
    assert episode["voices"]["NARRATOR"]["backend"] == "kokoro"


def test_write_project_preserves_existing_unless_forced(tmp_path):
    config = _make_book(tmp_path, [("chapters/01.md", "Hello world.")])
    plan = plan_audiobook(config, tmp_path)
    dest = tmp_path / "out"
    write_project(plan, dest)

    # Author hand-tunes the episode (casts a real voice).
    ep_path = dest / "chapter_01" / "episode.yaml"
    ep_path.write_text("title: tuned\n", encoding="utf-8")

    # Re-run without force: untouched.
    written = write_project(plan, dest)
    assert "chapter_01/episode.yaml" not in written
    assert ep_path.read_text(encoding="utf-8") == "title: tuned\n"

    # With force: overwritten.
    written = write_project(plan, dest, force=True)
    assert "chapter_01/episode.yaml" in written
    assert "tuned" not in ep_path.read_text(encoding="utf-8")


def test_write_project_unicode_roundtrip(tmp_path):
    """Spanish prose (the un-mundo saga) must survive JSON/YAML emit intact."""
    config = _make_book(
        tmp_path, [("chapters/01.md", "Vera viajó al norte. Hacía frío en la montaña.")]
    )
    plan = plan_audiobook(config, tmp_path)
    dest = tmp_path / "out"
    write_project(plan, dest)
    raw = (dest / "chapter_01" / "script.json").read_text(encoding="utf-8")
    assert "viajó" in raw and "frío" in raw and "montaña" in raw
    # ensure_ascii=False keeps accents human-readable, not escaped.
    assert "\\u" not in raw


def test_plan_is_pure_dataclass():
    """plan/AudiobookPlan stays a plain data object (no hidden I/O on access)."""
    plan = AudiobookPlan(project="p", episodes=[], voices={}, narrator="NARRATOR")
    assert plan.line_count == 0
    assert plan.char_count == 0


def test_inline_diagrams_are_not_narrated() -> None:
    """A house-style SVG diagram is visual apparatus, like a code listing."""
    md = (
        "Before the diagram.\n\n"
        '<div style="margin:1.6rem 0;">\n'
        '<svg viewBox="0 0 680 120" xmlns="http://www.w3.org/2000/svg">\n'
        '<text x="10" y="20">SOURCE CODE</text>\n'
        '<rect x="1" y="2" stroke-width="1.1"/>\n'
        "</svg>\n</div>\n\n"
        "After the diagram."
    )
    spoken = markdown_to_speech(md)
    assert "Before the diagram." in spoken
    assert "After the diagram." in spoken
    for leak in ("svg", "viewBox", "xmlns", "stroke-width", "<div", "rect"):
        assert leak not in spoken, f"{leak!r} reached the narrator"


def test_html_comments_are_not_narrated() -> None:
    assert "note to self" not in markdown_to_speech("Text.\n\n<!-- note to self -->\n\nMore.")


def test_inline_html_keeps_its_text() -> None:
    """Dropping a diagram is right; dropping a caption's words is not."""
    spoken = markdown_to_speech("<figure><figcaption>The chain, named once.</figcaption></figure>")
    assert "The chain, named once." in spoken


def test_tables_narrate_as_sentences_not_pipes() -> None:
    """A table's cells are the content; only its arrangement is visual."""
    md = (
        "| | Question | Where |\n"
        "|---|---|---|\n"
        "| 1 | Would this assumption flip the answer? | Chapter 8 |\n"
    )
    spoken = markdown_to_speech(md)
    assert "|" not in spoken
    assert "---" not in spoken
    assert "Would this assumption flip the answer?" in spoken
    assert "Chapter 8" in spoken


def test_a_table_row_gets_sentence_punctuation() -> None:
    spoken = markdown_to_speech("| Cost | Chapter 13 |\n")
    assert spoken.endswith(".")


def test_an_edited_chapter_regenerates_its_script(tmp_path):
    """The script is derived from the manuscript, so it must follow it.

    Skipping a script.json that merely exists means a corrected chapter
    regenerates to nothing and the stale text is then narrated as if current.
    """
    config = _make_book(tmp_path, [("chapters/01.md", "Hello world.")])
    dest = tmp_path / "out"
    write_project(plan_audiobook(config, tmp_path), dest)

    (tmp_path / "chapters" / "01.md").write_text("Hello, corrected world.", encoding="utf-8")
    written = write_project(plan_audiobook(config, tmp_path), dest)

    assert "chapter_01/script.json" in written
    assert "corrected" in (dest / "chapter_01" / "script.json").read_text(encoding="utf-8")


def test_an_unchanged_chapter_is_not_rewritten(tmp_path):
    config = _make_book(tmp_path, [("chapters/01.md", "Hello world.")])
    dest = tmp_path / "out"
    write_project(plan_audiobook(config, tmp_path), dest)
    assert write_project(plan_audiobook(config, tmp_path), dest) == []
