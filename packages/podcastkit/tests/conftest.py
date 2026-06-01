from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def tmp_episode(tmp_path: Path) -> Path:
    """A minimal episode directory with valid script.json and episode.yaml."""
    ep = tmp_path / "episode_01"
    ep.mkdir()

    script = [
        {"id": "narr_01", "character": "NARRATOR", "text": "It was a grey Tuesday."},
        {"id": "host_01", "character": "HOST", "text": "Right. Why are we here?"},
        {"id": "narr_02", "character": "NARRATOR", "text": "Nobody answered."},
    ]
    (ep / "script.json").write_text(json.dumps(script, indent=2), encoding="utf-8")

    config = {
        "title": "Test Episode",
        "output": "episode_01.mp3",
        "voices": {
            "NARRATOR": {"backend": "kokoro", "voice_id": "bm_george"},
            "HOST": {"backend": "kokoro", "voice_id": "af_bella"},
        },
        "timeline": [
            {"id": "narr_01", "pre_silence": 0.5},
            {"id": "host_01", "pre_silence": 0.5},
            {"id": "narr_02", "pre_silence": 0.5},
        ],
        "bg_tracks": [],
        "sfx_hits": [],
    }
    (ep / "episode.yaml").write_text(yaml.dump(config, allow_unicode=True), encoding="utf-8")

    return ep
