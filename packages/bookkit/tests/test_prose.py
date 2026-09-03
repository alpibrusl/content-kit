from __future__ import annotations

from bookkit.prose import check_prose, fix_commas


def kinds(findings) -> list[str]:
    return [f.kind for f in findings]


# --- comma before a restrictive because-clause -----------------------------


def test_restrictive_because_is_flagged() -> None:
    text = "It is worth knowing by name, because it is the answer to a question."
    assert "comma-before-because" in kinds(check_prose({1: text}))


def test_restrictive_because_is_fixed() -> None:
    fixed, n = fix_commas("It is worth knowing by name, because it is the answer.")
    assert n == 1
    assert fixed == "It is worth knowing by name because it is the answer."


def test_a_negated_main_clause_keeps_its_comma() -> None:
    """'He didn't leave, because he was angry' means the opposite without it."""
    text = "This gap does not exist, because engineers were hiding anything."
    assert check_prose({1: text}) == []
    assert fix_commas(text)[1] == 0


def test_an_elliptical_afterthought_keeps_its_comma() -> None:
    text = "That sentence should sound circular, because it is."
    assert fix_commas(text)[1] == 0


def test_a_clause_already_broken_by_an_em_dash_is_left_alone() -> None:
    text = "Covered in full in the next chapter — a whole one, because it deserves its own."
    assert fix_commas(text)[1] == 0


def test_whitespace_and_line_breaks_survive_the_fix() -> None:
    fixed, n = fix_commas("Keep the shape of that arrow,\nbecause every later chapter matters.")
    assert n == 1
    assert fixed == "Keep the shape of that arrow\nbecause every later chapter matters."


def test_code_and_diagrams_are_not_prose() -> None:
    for protected in (
        "```\nx = 1, because y\n```",
        '<svg viewBox="0 0 1 1">, because</svg>',
        "`a, because b`",
        "<!-- , because -->",
    ):
        assert check_prose({1: protected}) == [], protected
        assert fix_commas(protected)[1] == 0, protected


def test_the_fix_is_idempotent() -> None:
    once, first = fix_commas("It earns its place, because everything downstream inherits it.")
    twice, second = fix_commas(once)
    assert first == 1 and second == 0 and once == twice


# --- because, twice --------------------------------------------------------


def test_a_stumbled_repeat_is_flagged() -> None:
    text = (
        "It is worth being precise about why this exists, because it is not because anyone hid it."
    )
    assert "repeated-because" in kinds(check_prose({1: text}))


def test_a_correlative_pair_is_not_a_stumble() -> None:
    """'not because X, but because Y' is the shape of the sentence, not a slip."""
    for ok in (
        "Not because anyone hid them, but because nobody noticed.",
        "It works because the evidence favours it, or because nothing contradicts it.",
        "Chosen because most lenders reach for it, not because it is correct.",
    ):
        assert "repeated-because" not in kinds(check_prose({1: ok})), ok


def test_parallel_list_items_may_each_take_a_because() -> None:
    """Deliberate parallelism, not a stumble."""
    ok = (
        "A file that works because it happens to exist on your disk, "
        "a step that only works because you did something once and forgot."
    )
    assert "repeated-because" not in kinds(check_prose({1: ok}))


# --- reporting -------------------------------------------------------------


def test_findings_carry_their_chapter() -> None:
    findings = check_prose({7: "It earns its place, because everything downstream inherits it."})
    assert findings[0].chapter == 7
    assert findings[0].severity == "warning"
