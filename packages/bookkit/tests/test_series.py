from __future__ import annotations

from pathlib import Path

from bookkit.bible import BibleConfig, Character
from bookkit.series import (
    SeriesConfig,
    dump_series,
    load_series,
    merge_shared_characters,
    series_context_text,
)

SERIES = SeriesConfig.model_validate(
    {
        "series": "The Compliance Cycle",
        "arc": "The Engine moves from tool to author of the rules.",
        "shared_characters": [
            {"name": "MARA", "role": "protagonist", "voice": "Clipped."},
            {"name": "THE ENGINE", "role": "antagonist"},
        ],
        "books": [
            {
                "dir": "book-01",
                "title": "Audit",
                "role": "setup",
                "ends_with_state": [
                    {"character": "MARA", "set": {"status": "fugitive"}},
                    "The Engine edits its own logs.",
                ],
            },
            {"dir": "book-02", "title": "Anomaly", "role": "escalation", "opens_from": "book-01"},
        ],
    }
)


def test_book_lookup_and_string_coercion() -> None:
    b1 = SERIES.book("book-01")
    assert b1 is not None
    assert b1.ends_with_state[0].set == {"status": "fugitive"}
    assert b1.ends_with_state[1].note == "The Engine edits its own logs."


def test_series_context_includes_arc_and_predecessor_state() -> None:
    ctx = series_context_text(SERIES, "book-02")
    assert "The Compliance Cycle" in ctx
    assert "author of the rules" in ctx
    assert "follows 'Audit'" in ctx
    assert "MARA: {'status': 'fugitive'}" in ctx
    assert "The Engine edits its own logs." in ctx


def test_series_context_for_first_book_has_no_predecessor() -> None:
    ctx = series_context_text(SERIES, "book-01")
    assert "follows" not in ctx
    assert "ARC:" in ctx


def test_merge_shared_characters_appends_missing_keeps_local() -> None:
    local = BibleConfig(characters=[Character(name="MARA", voice="Local override voice.")])
    merged = merge_shared_characters(SERIES, local)
    names = [c.name for c in merged.characters]
    assert names == ["MARA", "THE ENGINE"]  # local MARA kept, ENGINE appended
    assert merged.character("MARA").voice == "Local override voice."


def test_dump_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "series.yaml"
    path.write_text(dump_series(SERIES), encoding="utf-8")
    reloaded = load_series(path)
    assert reloaded.series == "The Compliance Cycle"
    assert reloaded.book("book-02").opens_from == "book-01"
