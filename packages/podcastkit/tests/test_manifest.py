from __future__ import annotations

import json
from pathlib import Path

from podcastkit import _manifest


def test_digest_is_stable_and_text_sensitive() -> None:
    a = _manifest.text_digest("It works because everything downstream inherits it.")
    b = _manifest.text_digest("It works because everything downstream inherits it.")
    c = _manifest.text_digest("It works, because everything downstream inherits it.")
    assert a == b
    assert a != c, "a comma changes the narration, so it must change the digest"


def test_round_trip(tmp_path: Path) -> None:
    _manifest.save(tmp_path, {"narr_01_0001": "abc", "narr_01_0002": "def"})
    assert _manifest.load(tmp_path) == {"narr_01_0001": "abc", "narr_01_0002": "def"}


def test_a_missing_manifest_is_empty_not_an_error(tmp_path: Path) -> None:
    assert _manifest.load(tmp_path) == {}


def test_a_corrupt_manifest_is_empty_not_an_error(tmp_path: Path) -> None:
    (tmp_path / _manifest.MANIFEST_NAME).write_text("{not json", encoding="utf-8")
    assert _manifest.load(tmp_path) == {}


def test_a_manifest_from_a_future_version_is_ignored(tmp_path: Path) -> None:
    (tmp_path / _manifest.MANIFEST_NAME).write_text(
        json.dumps({"version": 999, "lines": {"x": "y"}}), encoding="utf-8"
    )
    assert _manifest.load(tmp_path) == {}


def test_status_distinguishes_the_three_cases() -> None:
    text = "The agent handled the part that looks like the work."
    recorded = {"known": _manifest.text_digest(text)}
    assert _manifest.status(recorded, "known", text) == "current"
    assert _manifest.status(recorded, "known", text + " Edited.") == "stale"
    assert _manifest.status(recorded, "never-seen", text) == "unverified"
