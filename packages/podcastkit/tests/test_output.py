"""Tests for _output.py — envelope helpers."""

from __future__ import annotations

import json
import time
from io import StringIO

from podcastkit._output import OutputFormat, emit, error_envelope, success_envelope

# ---------------------------------------------------------------------------
# success_envelope
# ---------------------------------------------------------------------------


def test_success_envelope_structure():
    env = success_envelope("generate", {"generated": 3, "skipped": 0})
    assert env["ok"] is True
    assert env["command"] == "generate"
    assert env["data"]["generated"] == 3
    assert "meta" in env
    assert "version" in env["meta"]


def test_success_envelope_duration_ms():
    t0 = time.time() - 1.0  # simulate 1 second ago
    env = success_envelope("assemble", {}, start_time=t0)
    assert env["meta"]["duration_ms"] >= 900


def test_success_envelope_dry_run():
    actions = [{"step": "check_ffmpeg", "ok": True}]
    env = success_envelope("assemble", {}, dry_run=True, planned_actions=actions)
    assert env["dry_run"] is True
    assert env["planned_actions"] == actions
    assert "data" not in env


# ---------------------------------------------------------------------------
# error_envelope
# ---------------------------------------------------------------------------


def test_error_envelope_structure():
    env = error_envelope("generate", code="NOT_FOUND", message="script.json missing")
    assert env["ok"] is False
    assert env["command"] == "generate"
    assert env["error"]["code"] == "NOT_FOUND"
    assert env["error"]["message"] == "script.json missing"


def test_error_envelope_with_hint():
    env = error_envelope("generate", code="NOT_FOUND", message="x", hint="run new first")
    assert env["error"]["hint"] == "run new first"


def test_error_envelope_with_hints_list():
    env = error_envelope("generate", code="NOT_FOUND", message="x", hints=["a", "b"])
    assert env["error"]["hints"] == ["a", "b"]


def test_error_envelope_no_hint():
    env = error_envelope("generate", code="NOT_FOUND", message="x")
    assert "hint" not in env["error"]
    assert "hints" not in env["error"]


# ---------------------------------------------------------------------------
# emit
# ---------------------------------------------------------------------------


def test_emit_json_writes_valid_json(monkeypatch):
    buf = StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    env = success_envelope("version", {"version": "0.1.0"})
    emit(env, OutputFormat.json)
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True


def test_emit_text_error_writes_to_stderr(monkeypatch, capsys):
    env = error_envelope("generate", code="NOT_FOUND", message="file missing", hint="try again")
    emit(env, OutputFormat.text)
    captured = capsys.readouterr()
    assert "NOT_FOUND" in captured.err
    assert "file missing" in captured.err
    assert "try again" in captured.err
