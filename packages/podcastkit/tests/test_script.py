"""Tests for _script.py — pure functions, no external deps."""

from __future__ import annotations

import pytest

from podcastkit._script import (
    derive_timeline,
    derive_voices_stub,
    extract_json,
    normalize_script,
)

# ---------------------------------------------------------------------------
# extract_json
# ---------------------------------------------------------------------------


def test_extract_json_raw_array():
    raw = '[{"id": "a", "character": "X", "text": "hello"}]'
    result = extract_json(raw)
    assert result == [{"id": "a", "character": "X", "text": "hello"}]


def test_extract_json_fenced_json():
    raw = '```json\n[{"id": "a", "character": "X", "text": "hi"}]\n```'
    result = extract_json(raw)
    assert len(result) == 1
    assert result[0]["id"] == "a"


def test_extract_json_fenced_no_lang():
    raw = '```\n[{"id": "b", "character": "Y", "text": "yo"}]\n```'
    result = extract_json(raw)
    assert result[0]["character"] == "Y"


def test_extract_json_embedded_in_prose():
    raw = (
        'Sure! Here is the script:\n[{"id": "c", "character": "Z", "text": "ok"}]\nHope that helps.'
    )
    result = extract_json(raw)
    assert result[0]["text"] == "ok"


def test_extract_json_no_array_raises():
    with pytest.raises(ValueError, match="No JSON array"):
        extract_json("Here is some prose with no array at all.")


def test_extract_json_invalid_json_raises():
    with pytest.raises(ValueError):
        extract_json("[{bad json}]")


# ---------------------------------------------------------------------------
# normalize_script
# ---------------------------------------------------------------------------


def test_normalize_script_basic():
    entries = [
        {"character": "narrator", "text": "Hello world."},
        {"character": "host", "text": "And hello back."},
    ]
    result = normalize_script(entries)
    assert result[0] == {"id": "narr_01", "character": "NARRATOR", "text": "Hello world."}
    assert result[1] == {"id": "host_01", "character": "HOST", "text": "And hello back."}


def test_normalize_script_ids_increment_per_character():
    entries = [
        {"character": "ARIA", "text": "Line one."},
        {"character": "NARRATOR", "text": "Line two."},
        {"character": "ARIA", "text": "Line three."},
        {"character": "ARIA", "text": "Line four."},
    ]
    result = normalize_script(entries)
    assert result[0]["id"] == "aria_01"
    assert result[1]["id"] == "narr_01"
    assert result[2]["id"] == "aria_02"
    assert result[3]["id"] == "aria_03"


def test_normalize_script_strips_whitespace():
    entries = [{"character": "  HOST  ", "text": "  hello  "}]
    result = normalize_script(entries)
    assert result[0]["character"] == "HOST"
    assert result[0]["text"] == "hello"


def test_normalize_script_missing_character_raises():
    with pytest.raises(ValueError, match="character"):
        normalize_script([{"text": "no character here"}])


def test_normalize_script_missing_text_raises():
    with pytest.raises(ValueError, match="text"):
        normalize_script([{"character": "HOST"}])


def test_normalize_script_non_dict_entry_raises():
    with pytest.raises(ValueError):
        normalize_script(["not a dict"])


# ---------------------------------------------------------------------------
# derive_timeline
# ---------------------------------------------------------------------------


def test_derive_timeline_default_silence():
    script = [
        {"id": "narr_01", "character": "NARRATOR", "text": "x"},
        {"id": "host_01", "character": "HOST", "text": "y"},
    ]
    result = derive_timeline(script)
    assert result == [
        {"id": "narr_01", "pre_silence": 0.5},
        {"id": "host_01", "pre_silence": 0.5},
    ]


def test_derive_timeline_ai_characters_get_longer_silence():
    script = [
        {"id": "narr_01", "character": "NARRATOR", "text": "x"},
        {"id": "aria_01", "character": "ARIA", "text": "y"},
        {"id": "narr_02", "character": "NARRATOR", "text": "z"},
    ]
    result = derive_timeline(script, ai_characters={"ARIA"})
    assert result[0]["pre_silence"] == 0.5  # NARRATOR — not AI
    assert result[1]["pre_silence"] == 1.2  # ARIA — AI
    assert result[2]["pre_silence"] == 0.5  # NARRATOR — not AI


def test_derive_timeline_empty_script():
    assert derive_timeline([]) == []


# ---------------------------------------------------------------------------
# derive_voices_stub
# ---------------------------------------------------------------------------


def test_derive_voices_stub_unique_characters():
    script = [
        {"id": "narr_01", "character": "NARRATOR", "text": "x"},
        {"id": "host_01", "character": "HOST", "text": "y"},
        {"id": "narr_02", "character": "NARRATOR", "text": "z"},
    ]
    stub = derive_voices_stub(script)
    assert set(stub.keys()) == {"NARRATOR", "HOST"}


def test_derive_voices_stub_has_backend():
    script = [{"id": "narr_01", "character": "NARRATOR", "text": "x"}]
    stub = derive_voices_stub(script)
    assert "backend" in stub["NARRATOR"]


def test_derive_voices_stub_empty():
    assert derive_voices_stub([]) == {}
