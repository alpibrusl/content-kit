from __future__ import annotations

from pathlib import Path

from bookkit.bible import BibleConfig
from bookkit.config import BookConfig
from bookkit.continuity import check_book, check_series
from bookkit.series import SeriesConfig


def _kinds(findings) -> set[str]:
    return {f.kind for f in findings}


def test_revenant_in_beats() -> None:
    bible = BibleConfig.model_validate(
        {
            "characters": [{"name": "TOMAS", "first_appears": 1}],
            "beats": [
                {
                    "chapter": 1,
                    "summary": "Tomas argues and leaves.",
                    "state_changes": [{"character": "TOMAS", "set": {"status": "departed"}}],
                },
                {"chapter": 3, "summary": "TOMAS returns to the office."},
            ],
        }
    )
    findings = check_book(bible)
    revenants = [f for f in findings if f.kind == "revenant"]
    assert len(revenants) == 1
    assert revenants[0].chapter == 3
    assert revenants[0].severity == "error"


def test_mourned_character_not_flagged_as_revenant() -> None:
    bible = BibleConfig.model_validate(
        {
            "characters": [{"name": "THEO", "first_appears": 1, "mourned": True}],
            "beats": [
                {
                    "chapter": 1,
                    "summary": "Theo skates.",
                    "state_changes": [{"character": "THEO", "set": {"status": "dead"}}],
                },
                {"chapter": 3, "summary": "The town mourns THEO at the funeral."},
            ],
        }
    )
    assert "revenant" not in _kinds(check_book(bible))


def test_revenant_cleared_by_revival() -> None:
    bible = BibleConfig.model_validate(
        {
            "characters": [{"name": "TOMAS", "first_appears": 1}],
            "beats": [
                {
                    "chapter": 1,
                    "state_changes": [{"character": "TOMAS", "set": {"status": "departed"}}],
                },
                {
                    "chapter": 2,
                    "state_changes": [{"character": "TOMAS", "set": {"status": "alive"}}],
                },
                {"chapter": 3, "summary": "TOMAS is back for good."},
            ],
        }
    )
    assert "revenant" not in _kinds(check_book(bible))


def test_unknown_character_drift_warns_with_suggestion() -> None:
    bible = BibleConfig.model_validate(
        {
            "characters": [{"name": "MARA"}],
            "beats": [
                {"chapter": 1, "state_changes": [{"character": "MARAH", "set": {"status": "gone"}}]}
            ],
        }
    )
    findings = [f for f in check_book(bible) if f.kind == "unknown-character"]
    assert findings and "MARA" in findings[0].detail


def test_duplicate_and_missing_and_out_of_range_beats() -> None:
    config = BookConfig(title="T", chapters=[{"file": "a.md"}, {"file": "b.md"}])
    bible = BibleConfig.model_validate({"beats": [{"chapter": 1}, {"chapter": 1}, {"chapter": 5}]})
    kinds = _kinds(check_book(bible, config))
    assert "duplicate-beat" in kinds  # chapter 1 twice
    assert "beat-out-of-range" in kinds  # chapter 5 > 2
    assert "missing-beat" in kinds  # chapter 2 has no beat


def test_scan_prose_detects_revenant_in_text(tmp_path: Path) -> None:
    (tmp_path / "chapters").mkdir()
    (tmp_path / "chapters" / "02-x.md").write_text(
        "# Two\n\nTOMAS walked back in, smiling.", encoding="utf-8"
    )
    bible = BibleConfig.model_validate(
        {
            "characters": [{"name": "TOMAS"}],
            "beats": [
                {
                    "chapter": 1,
                    "state_changes": [{"character": "TOMAS", "set": {"status": "dead"}}],
                },
                {"chapter": 2, "summary": "A quiet morning."},  # beat text doesn't mention him
            ],
        }
    )
    assert "revenant" not in _kinds(check_book(bible))  # beats clean
    assert "revenant" in _kinds(check_book(bible, book_dir=tmp_path, scan_prose=True))


def test_clean_book_has_no_findings() -> None:
    config = BookConfig(title="T", chapters=[{"file": "a.md"}])
    bible = BibleConfig.model_validate(
        {"characters": [{"name": "MARA"}], "beats": [{"chapter": 1, "summary": "Mara begins."}]}
    )
    assert check_book(bible, config) == []


def test_series_broken_and_self_handoff() -> None:
    series = SeriesConfig.model_validate(
        {
            "books": [
                {"dir": "book-01"},
                {"dir": "book-02", "opens_from": "ghost"},
                {"dir": "book-03", "opens_from": "book-03"},
            ]
        }
    )
    kinds = _kinds(check_series(series))
    assert "broken-handoff" in kinds
    assert "self-handoff" in kinds
