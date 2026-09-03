from __future__ import annotations

from bookkit._context import read_chapters
from bookkit.continuity import check_terms, strip_noise
from bookkit.glossary import render_glossary
from content_kit_core.ledger import LedgerConfig


def ledger(*concepts: dict) -> LedgerConfig:
    return LedgerConfig.model_validate({"concepts": list(concepts)})


def kinds(findings) -> list[str]:
    return [f.kind for f in findings]


C_IDEMPOTENT = {
    "term": "idempotent",
    "definition": "Safe to repeat.",
    "analogy": "A light switch labelled ON.",
    "defined_in": 8,
    "scan": True,
}


# --- ledger consistency, with no prose at all ------------------------------


def test_a_clean_ledger_reports_nothing() -> None:
    assert check_terms(ledger(C_IDEMPOTENT)) == []


def test_two_concepts_cannot_claim_the_same_name() -> None:
    findings = check_terms(
        ledger(
            {"term": "deploy", "definition": "d", "defined_in": 1},
            {"term": "release", "aka": ["deploy"], "definition": "d", "defined_in": 2},
        )
    )
    assert "term-defined-twice" in kinds(findings)


def test_a_prerequisite_must_resolve() -> None:
    findings = check_terms(
        ledger({"term": "a", "definition": "d", "defined_in": 2, "depends_on": ["ghost"]})
    )
    assert "term-never-defined" in kinds(findings)


def test_a_prerequisite_must_come_first() -> None:
    findings = check_terms(
        ledger(
            {"term": "a", "definition": "d", "defined_in": 2, "depends_on": ["b"]},
            {"term": "b", "definition": "d", "defined_in": 5},
        )
    )
    assert "prerequisite-inversion" in kinds(findings)


def test_a_concept_cannot_be_its_own_prerequisite() -> None:
    findings = check_terms(
        ledger({"term": "a", "definition": "d", "defined_in": 1, "depends_on": ["a"]})
    )
    assert "self-dependency" in kinds(findings)
    assert "prerequisite-inversion" not in kinds(findings)


def test_a_same_chapter_cycle_is_caught() -> None:
    """Two terms in one chapter that require each other have no backwards edge,
    so prerequisite-inversion cannot see them."""
    findings = check_terms(
        ledger(
            {"term": "a", "definition": "d", "defined_in": 3, "depends_on": ["b"]},
            {"term": "b", "definition": "d", "defined_in": 3, "depends_on": ["a"]},
        )
    )
    assert kinds(findings).count("dependency-cycle") == 1
    assert "prerequisite-inversion" not in kinds(findings)


def test_a_concept_with_no_definition_is_an_error() -> None:
    findings = check_terms(ledger({"term": "a", "defined_in": 1}))
    assert "concept-missing-definition" in kinds(findings)


def test_a_concept_with_no_chapter_is_an_error() -> None:
    """defined_in 0 would make every use 'after' the definition — a silent no-op."""
    findings = check_terms(ledger({"term": "a", "definition": "d"}))
    assert "defined-in-missing" in kinds(findings)


def test_defined_in_past_the_end_of_the_book_is_an_error() -> None:
    findings = check_terms(
        ledger({"term": "a", "definition": "d", "defined_in": 40}), n_chapters=16
    )
    assert "defined-in-out-of-range" in kinds(findings)


def test_missing_analogy_is_silent_unless_asked_for() -> None:
    spartan = ledger({"term": "a", "definition": "d", "defined_in": 1})
    assert "concept-missing-analogy" not in kinds(check_terms(spartan))
    assert "concept-missing-analogy" in kinds(check_terms(spartan, require_analogy=True))


def test_a_scan_list_must_name_real_aliases() -> None:
    findings = check_terms(
        ledger(
            {
                "term": "known-answer test",
                "definition": "d",
                "defined_in": 7,
                "scan": ["typo-answer test"],
            }
        )
    )
    assert "scan-name-unknown" in kinds(findings)


# --- prose rules -----------------------------------------------------------


def test_a_term_used_before_its_chapter_fails() -> None:
    findings = check_terms(
        ledger(C_IDEMPOTENT),
        {1: "Retrying is safe when the call is idempotent.", 8: "An idempotent call..."},
    )
    used = [f for f in findings if f.kind == "term-used-before-defined"]
    assert len(used) == 1
    assert used[0].chapter == 1
    assert used[0].severity == "error"


def test_a_signposted_forward_reference_is_allowed() -> None:
    findings = check_terms(
        ledger(C_IDEMPOTENT),
        {1: "Retries need idempotent calls (Chapter 8).", 8: "An idempotent call..."},
    )
    assert "term-used-before-defined" not in kinds(findings)


def test_a_plural_signpost_is_allowed() -> None:
    """The books write 'Chapters 6 and 7'; rejecting that punishes good writing."""
    findings = check_terms(
        ledger(C_IDEMPOTENT),
        {1: "Idempotent retries come later — Chapters 7 and 8.", 8: "An idempotent call..."},
    )
    assert "term-used-before-defined" not in kinds(findings)


def test_a_range_signpost_is_allowed() -> None:
    findings = check_terms(
        ledger(C_IDEMPOTENT),
        {1: "Idempotent work is covered in Chapters 6-9.", 8: "An idempotent call..."},
    )
    assert "term-used-before-defined" not in kinds(findings)


def test_a_through_range_signpost_is_allowed() -> None:
    findings = check_terms(
        ledger(C_IDEMPOTENT),
        {1: "Idempotent work — Chapters 7 through 10.", 8: "An idempotent call..."},
    )
    assert "term-used-before-defined" not in kinds(findings)


def test_a_signpost_to_a_different_chapter_does_not_count() -> None:
    findings = check_terms(
        ledger(C_IDEMPOTENT),
        {1: "Idempotent retries, as in Chapter 3.", 8: "An idempotent call..."},
    )
    assert "term-used-before-defined" in kinds(findings)


def test_use_in_code_or_a_diagram_is_not_prose() -> None:
    findings = check_terms(
        ledger(C_IDEMPOTENT),
        {
            1: '```\nidempotent = True\n```\n\n<svg xmlns="http://idempotent"></svg>',
            8: "An idempotent call is safe to repeat.",
        },
    )
    assert "term-used-before-defined" not in kinds(findings)


def test_an_unused_concept_is_a_warning_not_an_error() -> None:
    findings = check_terms(ledger(C_IDEMPOTENT), {1: "Nothing relevant here.", 8: "Still not."})
    orphans = [f for f in findings if f.kind == "orphan-concept"]
    assert len(orphans) == 1
    assert orphans[0].severity == "warning"


def test_a_reference_past_the_end_of_the_book_is_an_error() -> None:
    """Inserting a chapter renumbers everything after it; the prose does not
    follow, and the signpost hatch would otherwise accept the wrong number."""
    findings = check_terms(
        ledger(C_IDEMPOTENT),
        {8: "An idempotent call is safe. The standards for this are in Chapter 19."},
        n_chapters=8,
    )
    bad = [f for f in findings if f.kind == "chapter-reference-out-of-range"]
    assert len(bad) == 1
    assert bad[0].severity == "error"
    assert bad[0].chapter == 8


def test_an_in_range_reference_is_fine() -> None:
    findings = check_terms(
        ledger(C_IDEMPOTENT),
        {8: "An idempotent call is safe. See Chapter 3 and Chapters 5 to 7."},
        n_chapters=8,
    )
    assert "chapter-reference-out-of-range" not in kinds(findings)


def test_a_sibling_volume_is_not_this_book() -> None:
    """'Chapter 7 of the third book in this series' cites another volume,
    whose chapter count is none of this book's business."""
    findings = check_terms(
        ledger(C_IDEMPOTENT),
        {8: "An idempotent call is safe, as Chapter 19 of the third book in this series shows."},
        n_chapters=8,
    )
    assert "chapter-reference-out-of-range" not in kinds(findings)


def test_references_are_not_checked_without_a_chapter_count() -> None:
    """While a book is an outline there is nothing to be out of range of."""
    findings = check_terms(ledger(C_IDEMPOTENT), {8: "See Chapter 40."})
    assert "chapter-reference-out-of-range" not in kinds(findings)


def test_a_chapter_that_defines_nothing_is_a_warning() -> None:
    findings = check_terms(
        ledger(C_IDEMPOTENT), {8: "An idempotent call is safe.", 9: "Some prose."}
    )
    empty = [f for f in findings if f.kind == "chapter-defines-nothing"]
    assert [f.chapter for f in empty] == [9]


def test_a_declared_term_free_chapter_is_not_nagged_about() -> None:
    """A closing checklist recaps the book; saying so once beats a forever-warning."""
    led = LedgerConfig.model_validate({"concepts": [C_IDEMPOTENT], "teaches_no_terms": [9]})
    findings = check_terms(led, {8: "An idempotent call is safe.", 9: "Some prose."})
    assert "chapter-defines-nothing" not in kinds(findings)


def test_a_stale_term_free_declaration_is_flagged() -> None:
    led = LedgerConfig.model_validate({"concepts": [C_IDEMPOTENT], "teaches_no_terms": [8]})
    findings = check_terms(led, {8: "An idempotent call is safe."})
    assert "stale-teaches-no-terms" in kinds(findings)


def test_an_ordinary_word_alias_does_not_fail_the_build() -> None:
    """The whole reason scanning is conservative: 'sanity-check' is also a verb."""
    concept = {
        "term": "known-answer test",
        "aka": ["sanity check"],
        "definition": "d",
        "defined_in": 7,
        "scan": ["known-answer test"],
    }
    findings = check_terms(
        ledger(concept),
        {1: "You still had to sanity-check what came out.", 7: "A known-answer test is..."},
    )
    assert "term-used-before-defined" not in kinds(findings)


def test_strip_noise_leaves_ordinary_prose_alone() -> None:
    assert "real sentence" in strip_noise("A real sentence with `code` in it.")


# --- reading a real book directory -----------------------------------------


def test_read_chapters_numbers_by_filename(tmp_book) -> None:
    chapters = read_chapters(tmp_book)
    assert sorted(chapters) == [1, 2]
    assert "first" in chapters[1]


# --- the generated glossary ------------------------------------------------


def test_render_glossary_is_sorted_and_complete() -> None:
    out = render_glossary(
        ledger(
            C_IDEMPOTENT,
            {"term": "artifact", "definition": "A built file.", "defined_in": 2, "aka": ["build"]},
        )
    )
    assert out.index("**artifact**") < out.index("**idempotent**")
    assert "*(ch. 2)*" in out
    assert "also called build" in out
    assert ": Safe to repeat." in out
    assert "*A light switch labelled ON.*" in out


def test_render_glossary_folds_wrapped_yaml_scalars() -> None:
    out = render_glossary(ledger({"term": "a", "definition": "one\ntwo\nthree", "defined_in": 1}))
    assert ": one two three" in out
