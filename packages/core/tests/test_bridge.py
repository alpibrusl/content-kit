from __future__ import annotations

import pytest

from content_kit_core._errors import PreconditionError
from content_kit_core.bridge import (
    EpisodeConfig,
    ScriptLine,
    validate_episode,
    validate_script,
)

MINIMAL_EPISODE = {
    "title": "Chapter 1",
    "output": "chapter_01.mp3",
    "voices": {"NARRATOR": {"backend": "kokoro", "voice_id": "bm_george"}},
    "timeline": [{"id": "narr_01_0001", "pre_silence": 1.0}],
}


def test_validate_episode_accepts_a_producer_emitted_doc() -> None:
    config = validate_episode(MINIMAL_EPISODE)
    assert isinstance(config, EpisodeConfig)
    assert config.voices["NARRATOR"].backend == "kokoro"


def test_validate_episode_ignores_extra_voice_note() -> None:
    # bookkit seeds cast voices with a free-text `note`; the contract tolerates it.
    doc = {
        **MINIMAL_EPISODE,
        "voices": {"ALICE": {"backend": "kokoro", "voice_id": "REPLACE_ME", "note": "wry"}},
    }
    assert validate_episode(doc).voices["ALICE"].voice_id == "REPLACE_ME"


def test_validate_episode_rejects_unknown_backend() -> None:
    bad = {**MINIMAL_EPISODE, "voices": {"N": {"backend": "whisper", "voice_id": "x"}}}
    with pytest.raises(PreconditionError, match="audio bridge contract"):
        validate_episode(bad)


def test_validate_script_round_trips() -> None:
    lines = validate_script([{"id": "narr_01", "character": "NARRATOR", "text": "Hi."}])
    assert lines == [ScriptLine(id="narr_01", character="NARRATOR", text="Hi.")]


def test_validate_script_requires_text() -> None:
    with pytest.raises(PreconditionError, match="audio bridge contract"):
        validate_script([{"id": "narr_01", "character": "NARRATOR"}])
