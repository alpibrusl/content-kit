from __future__ import annotations

from pathlib import Path

import yaml

from bookkit.duplication import check_duplication, compare, sentences

SHARED = (
    "Arithmetic done by pattern matching instead of by running actual code is the "
    "single most avoidable way a result fails to become trustworthy. "
    "An agent produces a response one piece at a time, each chosen because it is "
    "the most plausible continuation of everything written so far. "
    "For most of what it writes, plausible and correct are the same thing. "
)
DISTINCT = (
    "A randomised holdout is the only comparison that survives contact with a "
    "seasonal effect nobody remembered to control for. "
    "Bellwood ran its checkout test through December, which is why the lift "
    "looked so implausibly large in the first place. "
    "The dashboard did not turn red, because a dashboard cannot know that. "
)


def _book(root: Path, chapters: dict[str, str]) -> Path:
    (root / "chapters").mkdir(parents=True)
    entries = []
    for name, body in chapters.items():
        (root / "chapters" / name).write_text(f"# Heading\n\n{body}\n", encoding="utf-8")
        entries.append({"file": f"chapters/{name}", "title": ""})
    (root / "book.yaml").write_text(
        yaml.dump({"title": root.name, "chapters": entries}), encoding="utf-8"
    )
    return root


# --- sentence extraction ---------------------------------------------------


def test_short_sentences_are_not_evidence() -> None:
    """'That is the point.' recurs in unrelated prose all the time."""
    assert sentences("That is the point. It works.") == []


def test_code_and_diagrams_are_not_compared() -> None:
    md = "```\nsome code that repeats verbatim across both books entirely\n```"
    assert sentences(md) == []


# --- the comparison --------------------------------------------------------


def test_a_reused_chapter_is_reported(tmp_path: Path) -> None:
    a = _book(tmp_path / "evidence", {"04-compute.md": SHARED})
    b = _book(tmp_path / "ledger", {"04-compute.md": SHARED})
    findings = check_duplication(a, b)
    assert [f.kind for f in findings] == ["duplicate-chapter"]
    assert findings[0].severity == "warning"


def test_an_independently_written_chapter_is_not(tmp_path: Path) -> None:
    a = _book(tmp_path / "evidence", {"08-fair.md": DISTINCT})
    b = _book(tmp_path / "ledger", {"08-assumption.md": SHARED})
    assert check_duplication(a, b) == []


def test_a_chapter_that_moved_is_still_found(tmp_path: Path) -> None:
    """Comparing like-for-like chapter numbers would miss this entirely."""
    a = _book(tmp_path / "evidence", {"11-chart.md": SHARED})
    b = _book(tmp_path / "ledger", {"01-other.md": DISTINCT, "12-chart.md": SHARED})
    overlaps = {o.chapter: o for o in compare({11: SHARED}, {1: DISTINCT, 12: SHARED})}
    assert overlaps[11].other_chapter == 12
    assert check_duplication(a, b)[0].detail.endswith(
        "let each book earn its own examples and failure cases"
    )


def test_the_threshold_is_honoured(tmp_path: Path) -> None:
    """Half the chapter is shared: reported at 0.4, silent at 0.6."""
    a = _book(tmp_path / "evidence", {"04-c.md": SHARED + DISTINCT})
    b = _book(tmp_path / "ledger", {"04-c.md": SHARED})
    assert check_duplication(a, b, threshold=0.6) == []
    assert check_duplication(a, b, threshold=0.4)


def test_rewriting_a_sentence_lowers_the_count(tmp_path: Path) -> None:
    """The measure has to fall when the author does the work, or it is not
    measuring the thing anyone cares about."""
    rewritten = SHARED.replace(
        "Arithmetic done by pattern matching instead of by running actual code",
        "A number narrated from memory rather than computed by a formula",
    ).replace(
        "An agent produces a response one piece at a time, each chosen because it is "
        "the most plausible continuation of everything written so far.",
        "The model emits one token after another, picking whichever looks likeliest "
        "given the words that came before it.",
    )
    before = compare({4: SHARED}, {4: SHARED})[0].ratio
    after = compare({4: rewritten}, {4: SHARED})[0].ratio
    assert before == 1.0
    assert after < before
