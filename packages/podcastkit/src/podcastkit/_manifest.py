"""What each rendered voice line was actually synthesized from.

A voice line is cached on disk as ``voices/<line_id>.mp3``, and a line id
survives an edit to its text. Without a record of the words behind each file,
"the file exists" is the only available answer to "is this current?", so
correcting a sentence in the script leaves the old audio in place, silently and
permanently. That is the wrong failure: the render looks like it succeeded, and
the mistake only surfaces when somebody listens.

This module keeps a small sidecar next to the audio mapping each line id to a
hash of the text it was rendered from, which turns the question into one that
can be answered.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

MANIFEST_NAME = ".manifest.json"
_VERSION = 1


def text_digest(text: str) -> str:
    """A short, stable digest of a line's text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def load(voices_dir: Path) -> dict[str, str]:
    """Line id -> digest, for whatever has been recorded so far.

    A missing or unreadable manifest is an empty record, never an error: a
    project rendered before this existed is simply unverifiable, not broken.
    """
    path = voices_dir / MANIFEST_NAME
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict) or raw.get("version") != _VERSION:
        return {}
    lines = raw.get("lines")
    return lines if isinstance(lines, dict) else {}


def save(voices_dir: Path, digests: dict[str, str]) -> None:
    """Write the record, pruned to the lines that currently exist."""
    voices_dir.mkdir(parents=True, exist_ok=True)
    payload = {"version": _VERSION, "lines": dict(sorted(digests.items()))}
    (voices_dir / MANIFEST_NAME).write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")


def status(recorded: dict[str, str], line_id: str, text: str) -> str:
    """One of ``current`` | ``stale`` | ``unverified`` for an existing file."""
    known = recorded.get(line_id)
    if known is None:
        return "unverified"
    return "current" if known == text_digest(text) else "stale"
