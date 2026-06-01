"""Tests for config.py — Pydantic model validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from podcastkit.config import EpisodeConfig, VoiceConfig

MINIMAL_CONFIG = {
    "title": "Episode 1",
    "output": "episode_01.mp3",
    "voices": {
        "NARRATOR": {"backend": "kokoro", "voice_id": "bm_george"},
    },
    "timeline": [{"id": "narr_01", "pre_silence": 0.5}],
    "bg_tracks": [],
    "sfx_hits": [],
}


# ---------------------------------------------------------------------------
# VoiceConfig
# ---------------------------------------------------------------------------


def test_voice_config_valid_backends():
    for backend in ("chatterbox", "elevenlabs", "kokoro", "openai"):
        vc = VoiceConfig(backend=backend, voice_id="test_voice")
        assert vc.backend == backend


def test_voice_config_invalid_backend_raises():
    with pytest.raises(ValidationError):
        VoiceConfig(backend="whisper", voice_id="test")


def test_voice_config_defaults():
    vc = VoiceConfig(backend="kokoro", voice_id="bm_george")
    assert vc.model_id == ""
    assert vc.settings == {}


# ---------------------------------------------------------------------------
# EpisodeConfig
# ---------------------------------------------------------------------------


def test_episode_config_valid():
    config = EpisodeConfig.model_validate(MINIMAL_CONFIG)
    assert config.title == "Episode 1"
    assert config.output == "episode_01.mp3"
    assert "NARRATOR" in config.voices
    assert config.voices["NARRATOR"].backend == "kokoro"
    assert len(config.timeline) == 1
    assert config.timeline[0].id == "narr_01"
    assert config.timeline[0].pre_silence == 0.5


def test_episode_config_defaults():
    config = EpisodeConfig.model_validate({"voices": {}, "timeline": []})
    assert config.title == ""
    assert config.output == "episode.mp3"
    assert config.bg_tracks == []
    assert config.sfx_hits == []


def test_episode_config_multiple_voices():
    raw = {
        **MINIMAL_CONFIG,
        "voices": {
            "NARRATOR": {"backend": "kokoro", "voice_id": "bm_george"},
            "HOST": {"backend": "openai", "voice_id": "nova", "model_id": "tts-1-hd"},
        },
        "timeline": [
            {"id": "narr_01", "pre_silence": 0.5},
            {"id": "host_01", "pre_silence": 1.2},
        ],
    }
    config = EpisodeConfig.model_validate(raw)
    assert len(config.voices) == 2
    assert config.voices["HOST"].model_id == "tts-1-hd"
    assert config.timeline[1].pre_silence == 1.2


def test_episode_config_voice_settings():
    raw = {
        **MINIMAL_CONFIG,
        "voices": {
            "NARRATOR": {
                "backend": "elevenlabs",
                "voice_id": "abc123",
                "model_id": "eleven_multilingual_v2",
                "settings": {"stability": 0.7, "similarity_boost": 0.75},
            }
        },
    }
    config = EpisodeConfig.model_validate(raw)
    assert config.voices["NARRATOR"].settings["stability"] == 0.7
