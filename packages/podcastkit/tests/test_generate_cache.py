"""The cache must follow the script, not just the filename.

A voice line is stored as ``voices/<line_id>.mp3`` and a line id survives an
edit to its text, so before the manifest existed, correcting a sentence left the
old audio in place with no sign anything was wrong.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from podcastkit import _manifest
from podcastkit.cli import app

runner = CliRunner()


@pytest.fixture
def fake_tts(monkeypatch):
    """A backend that writes the line's own text into the file, so a test can
    read back which words a given .mp3 was rendered from."""
    rendered: list[str] = []

    class FakeBackend:
        def synthesize(self, text: str, voice, dest: Path) -> None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(text.encode("utf-8").ljust(6 * 1024, b"\0"))
            rendered.append(text)

    monkeypatch.setattr("podcastkit.cli.get_backend", lambda name: FakeBackend())
    return rendered


def _script(ep: Path) -> list[dict]:
    return json.loads((ep / "script.json").read_text())


def _rewrite_first_line(ep: Path, new_text: str) -> None:
    script = _script(ep)
    script[0]["text"] = new_text
    (ep / "script.json").write_text(json.dumps(script, indent=2), encoding="utf-8")


def _audio_text(ep: Path, line_id: str) -> str:
    return (ep / "voices" / f"{line_id}.mp3").read_bytes().rstrip(b"\0").decode("utf-8")


def test_first_run_renders_everything_and_records_it(tmp_episode: Path, fake_tts) -> None:
    result = runner.invoke(app, ["generate", "-e", str(tmp_episode)])
    assert result.exit_code == 0, result.stdout
    assert len(fake_tts) == 3
    recorded = _manifest.load(tmp_episode / "voices")
    assert set(recorded) == {"narr_01", "host_01", "narr_02"}


def test_an_unchanged_rerun_renders_nothing(tmp_episode: Path, fake_tts) -> None:
    runner.invoke(app, ["generate", "-e", str(tmp_episode)])
    fake_tts.clear()
    result = runner.invoke(app, ["generate", "-e", str(tmp_episode)])
    assert result.exit_code == 0, result.stdout
    assert fake_tts == [], "unchanged lines must still be cached"


def test_an_edited_line_is_re_rendered(tmp_episode: Path, fake_tts) -> None:
    """The bug: this used to keep the old audio forever."""
    runner.invoke(app, ["generate", "-e", str(tmp_episode)])
    fake_tts.clear()

    _rewrite_first_line(tmp_episode, "It was a grey Tuesday in November.")
    result = runner.invoke(app, ["generate", "-e", str(tmp_episode)])

    assert result.exit_code == 0, result.stdout
    assert fake_tts == ["It was a grey Tuesday in November."]
    assert _audio_text(tmp_episode, "narr_01") == "It was a grey Tuesday in November."
    assert "Re-rendered (text changed): 1" in result.stdout


def test_editing_one_line_leaves_the_others_cached(tmp_episode: Path, fake_tts) -> None:
    runner.invoke(app, ["generate", "-e", str(tmp_episode)])
    fake_tts.clear()
    _rewrite_first_line(tmp_episode, "Something else entirely.")
    runner.invoke(app, ["generate", "-e", str(tmp_episode)])
    assert len(fake_tts) == 1, "only the edited line should cost anything"


def test_audio_predating_the_manifest_is_adopted_and_reported(tmp_episode: Path, fake_tts) -> None:
    """A project rendered before this existed is adopted, not re-rendered —
    re-synthesizing every line would be a surprise bill on a paid backend."""
    runner.invoke(app, ["generate", "-e", str(tmp_episode)])
    (tmp_episode / "voices" / _manifest.MANIFEST_NAME).unlink()
    fake_tts.clear()

    result = runner.invoke(app, ["generate", "-e", str(tmp_episode)])
    assert fake_tts == [], "must not re-render, and must not bill anyone by surprise"
    assert "adopted as a baseline" in result.stdout
    assert "--force" in result.stdout


def test_an_edit_after_adoption_is_caught(tmp_episode: Path, fake_tts) -> None:
    """Adoption exists to make this work: never recording a baseline would
    leave a legacy project permanently blind to its own edits."""
    runner.invoke(app, ["generate", "-e", str(tmp_episode)])
    (tmp_episode / "voices" / _manifest.MANIFEST_NAME).unlink()
    runner.invoke(app, ["generate", "-e", str(tmp_episode)])  # adopts
    fake_tts.clear()

    _rewrite_first_line(tmp_episode, "Edited after adoption.")
    result = runner.invoke(app, ["generate", "-e", str(tmp_episode)])
    assert fake_tts == ["Edited after adoption."]
    assert _audio_text(tmp_episode, "narr_01") == "Edited after adoption."
    assert "Re-rendered (text changed): 1" in result.stdout


def test_force_still_re_renders_everything(tmp_episode: Path, fake_tts) -> None:
    runner.invoke(app, ["generate", "-e", str(tmp_episode)])
    fake_tts.clear()
    runner.invoke(app, ["generate", "-e", str(tmp_episode), "--force"])
    assert len(fake_tts) == 3


def test_the_manifest_does_not_outlive_its_audio(tmp_episode: Path, fake_tts) -> None:
    """A line dropped from the script leaves no entry behind."""
    runner.invoke(app, ["generate", "-e", str(tmp_episode)])
    script = _script(tmp_episode)[:2]
    (tmp_episode / "script.json").write_text(json.dumps(script, indent=2), encoding="utf-8")
    runner.invoke(app, ["generate", "-e", str(tmp_episode)])
    assert set(_manifest.load(tmp_episode / "voices")) == {"narr_01", "host_01"}


def _final_envelope(stdout: str) -> dict:
    """The last JSON object on stdout — progress lines are NDJSON before it."""
    decoder = json.JSONDecoder()
    idx, last = 0, None
    while (start := stdout.find("{", idx)) != -1:
        try:
            obj, end = decoder.raw_decode(stdout, start)
        except json.JSONDecodeError:
            idx = start + 1
            continue
        last, idx = obj, end
    assert last is not None, stdout
    return last


def test_json_output_reports_the_counters(tmp_episode: Path, fake_tts) -> None:
    runner.invoke(app, ["generate", "-e", str(tmp_episode)])
    _rewrite_first_line(tmp_episode, "Edited.")
    result = runner.invoke(app, ["generate", "-e", str(tmp_episode), "-o", "json"])
    payload = _final_envelope(result.stdout)
    assert payload["data"]["restaled"] == 1
    assert payload["data"]["skipped"] == 2
