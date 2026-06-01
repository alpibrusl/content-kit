"""CLI integration tests — use typer's CliRunner (no TTS, no ffmpeg)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from podcastkit.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


def test_version_text():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "podcastkit" in result.output
    assert "0.1.0" in result.output


def test_version_json():
    result = runner.invoke(app, ["version", "--output", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["ok"] is True
    assert data["data"]["version"] == "0.1.0"


# ---------------------------------------------------------------------------
# introspect
# ---------------------------------------------------------------------------


def test_introspect_returns_valid_json():
    result = runner.invoke(app, ["introspect"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["ok"] is True
    commands = [c["name"] for c in data["data"]["commands"]]
    assert "generate" in commands
    assert "assemble" in commands
    assert "new" in commands


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------


def test_new_creates_episode_files(tmp_path):
    result = runner.invoke(app, ["new", "my-show", "--dest", str(tmp_path)])
    assert result.exit_code == 0
    ep_dir = tmp_path / "my-show" / "episode_01"
    assert (ep_dir / "episode.yaml").exists()
    assert (ep_dir / "script.json").exists()


def test_new_multi_episode(tmp_path):
    result = runner.invoke(app, ["new", "big-show", "--episodes", "3", "--dest", str(tmp_path)])
    assert result.exit_code == 0
    project = tmp_path / "big-show"
    for ep in ("episode_01", "episode_02", "episode_03"):
        assert (project / ep / "episode.yaml").exists()


def test_new_json_output(tmp_path):
    result = runner.invoke(app, ["new", "test", "--dest", str(tmp_path), "--output", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["ok"] is True
    assert data["data"]["project"] == "test"


# ---------------------------------------------------------------------------
# generate — error paths (no TTS called)
# ---------------------------------------------------------------------------


def test_generate_missing_episode_yaml(tmp_path):
    result = runner.invoke(app, ["generate", "--episode-dir", str(tmp_path)])
    assert result.exit_code != 0


def test_generate_missing_script_json(tmp_path):
    (tmp_path / "episode.yaml").write_text(
        "title: test\noutput: ep.mp3\nvoices: {}\ntimeline: []\nbg_tracks: []\nsfx_hits: []\n"
    )
    result = runner.invoke(app, ["generate", "--episode-dir", str(tmp_path)])
    assert result.exit_code != 0


def test_generate_missing_voice_config(tmp_episode: Path):
    """Script has characters not in episode.yaml voices → INVALID_ARGS."""
    import yaml

    config = yaml.safe_load((tmp_episode / "episode.yaml").read_text())
    del config["voices"]["HOST"]  # HOST is in script but now missing from voices
    (tmp_episode / "episode.yaml").write_text(yaml.dump(config))

    result = runner.invoke(app, ["generate", "--episode-dir", str(tmp_episode)])
    assert result.exit_code != 0


def test_generate_dry_run_no_api_calls(tmp_episode: Path):
    """Dry run should plan actions without calling any TTS backend."""
    result = runner.invoke(app, ["generate", "--episode-dir", str(tmp_episode), "--dry-run"])
    # Exit code 9 = DRY_RUN
    assert result.exit_code == 9
    assert "narr_01" in result.output


def test_generate_dry_run_json(tmp_episode: Path):
    result = runner.invoke(
        app, ["generate", "--episode-dir", str(tmp_episode), "--dry-run", "--output", "json"]
    )
    assert result.exit_code == 9
    data = json.loads(result.output)
    assert data["dry_run"] is True
    ids = [a["id"] for a in data["planned_actions"]]
    assert "narr_01" in ids


# ---------------------------------------------------------------------------
# assemble — error paths (no ffmpeg called)
# ---------------------------------------------------------------------------


def test_assemble_missing_episode_yaml(tmp_path):
    result = runner.invoke(app, ["assemble", "--episode-dir", str(tmp_path)])
    assert result.exit_code != 0


def test_assemble_dry_run(tmp_episode: Path):
    """Dry run reports missing voice files without running ffmpeg."""
    result = runner.invoke(app, ["assemble", "--episode-dir", str(tmp_episode), "--dry-run"])
    # Exit code is either 8 (missing voices) or 9 (dry run OK)
    assert result.exit_code in (8, 9)
    assert "voices" in result.output
