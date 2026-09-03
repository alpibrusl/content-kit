"""Pass 1's scratch WAV should not outlive the MP3 it was used to build.

It is roughly seven times the size of the finished episode, so a book-length
project leaves gigabytes of it behind — all of it regenerable, none of it read
again once assembly succeeds.
"""

from __future__ import annotations

from pathlib import Path

from podcastkit.assemble import discard_intermediate


def _scratch(episode: Path, size: int = 4096) -> Path:
    build = episode / "build"
    build.mkdir(parents=True, exist_ok=True)
    track = build / "voices_track.wav"
    track.write_bytes(b"\0" * size)
    return track


def test_it_removes_the_track_and_reports_the_bytes(tmp_path: Path) -> None:
    track = _scratch(tmp_path, 8192)
    freed = discard_intermediate(tmp_path)
    assert freed == 8192
    assert not track.exists()


def test_it_removes_the_build_dir_when_nothing_else_is_there(tmp_path: Path) -> None:
    _scratch(tmp_path)
    discard_intermediate(tmp_path)
    assert not (tmp_path / "build").exists()


def test_it_keeps_the_build_dir_when_something_else_is_there(tmp_path: Path) -> None:
    _scratch(tmp_path)
    (tmp_path / "build" / "mix_notes.txt").write_text("keep me", encoding="utf-8")
    discard_intermediate(tmp_path)
    assert (tmp_path / "build").exists()
    assert (tmp_path / "build" / "mix_notes.txt").read_text() == "keep me"


def test_it_is_safe_to_call_when_there_is_nothing_to_remove(tmp_path: Path) -> None:
    assert discard_intermediate(tmp_path) == 0
    _scratch(tmp_path)
    discard_intermediate(tmp_path)
    assert discard_intermediate(tmp_path) == 0
