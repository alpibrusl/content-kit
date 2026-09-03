from __future__ import annotations

import re

import pytest

from content_kit_core.ledger import Concept, LedgerConfig, dump_ledger, load_ledger, name_pattern


def matches(term: str, text: str) -> bool:
    return bool(re.search(name_pattern(term), text, re.I))


# --- inflection ------------------------------------------------------------


@pytest.mark.parametrize(
    ("term", "text"),
    [
        ("environment variable", "two environment variables"),
        ("dependency", "the dependencies list"),
        ("retry", "three retries later"),
        ("anomaly", "cost anomalies"),
        ("analysis", "both analyses agreed"),
        ("hypothesis", "competing hypotheses"),
        ("bias", "several biases"),
        ("batch", "nightly batches"),
        ("index", "the indexes rebuilt"),
    ],
)
def test_plurals_are_matched(term: str, text: str) -> None:
    """A gate that matches 'dependency' but not 'dependencies' has an invisible hole."""
    assert matches(term, text)


def test_singular_still_matches() -> None:
    assert matches("dependency", "a single dependency")
    assert matches("analysis", "one analysis")


def test_matching_does_not_bleed_into_longer_words() -> None:
    assert not matches("test", "testify")
    assert not matches("bias", "biassed-looking")  # word boundary, not a prefix match


# --- separators ------------------------------------------------------------


@pytest.mark.parametrize("written", ["trade-off", "trade off", "tradeoff", "trade-offs"])
def test_hyphenated_terms_match_every_spelling(written: str) -> None:
    assert matches("trade-off", f"the {written} was clear")


def test_space_separated_terms_require_a_separator() -> None:
    assert matches("objective function", "the objective function")
    assert matches("objective function", "the objective-function")
    assert not matches("objective function", "the objectivefunction")


def test_multi_word_terms_survive_a_line_break() -> None:
    """A hard-wrapped manuscript can break a line mid-term; that is not an escape."""
    assert matches("known-answer test", "run a known-answer\ntest before trusting it")


def test_only_the_last_word_is_inflected() -> None:
    assert matches("environment variable", "environment variables")
    assert not matches("environment variable", "environments variable")


def test_empty_name_never_matches() -> None:
    assert not matches("", "anything at all")
    assert not matches("   ", "anything at all")


# --- scannable names -------------------------------------------------------


def test_ordinary_single_words_are_not_scanned_by_default() -> None:
    """Flagging 'test' or 'state' would train everyone to ignore the gate."""
    assert Concept(term="test", definition="d", defined_in=1).scannable_names == []


def test_distinctive_shapes_are_scanned_by_default() -> None:
    assert Concept(term="objective function", definition="d", defined_in=1).scannable_names
    assert Concept(term="trade-off", definition="d", defined_in=1).scannable_names
    assert Concept(term="CI/CD", definition="d", defined_in=1).scannable_names


def test_scan_true_opts_in_the_term_but_not_its_synonyms() -> None:
    c = Concept(
        term="idempotent",
        aka=["repeatable"],
        definition="d",
        defined_in=1,
        scan=True,
    )
    assert c.scannable_names == ["idempotent"]


def test_scan_false_opts_out_entirely() -> None:
    c = Concept(term="objective function", definition="d", defined_in=1, scan=False)
    assert c.scannable_names == []


def test_scan_list_keeps_the_useful_name_and_drops_the_ordinary_one() -> None:
    """'sanity check' is both a good alias and an ordinary English verb."""
    c = Concept(
        term="known-answer test",
        aka=["sanity check"],
        definition="d",
        defined_in=7,
        scan=["known-answer test"],
    )
    assert c.scannable_names == ["known-answer test"]


# --- the model itself ------------------------------------------------------


def test_lookup_by_term_or_alias_is_case_insensitive() -> None:
    ledger = LedgerConfig(
        concepts=[Concept(term="idempotent", aka=["idempotence"], definition="d", defined_in=8)]
    )
    assert ledger.concept("IDEMPOTENT") is not None
    assert ledger.concept("Idempotence") is not None
    assert ledger.concept("nonexistent") is None


def test_load_and_dump_round_trip(tmp_path) -> None:
    path = tmp_path / "glossary.yaml"
    path.write_text(
        "kind: technical\n"
        "title: A Book\n"
        "concepts:\n"
        "  - term: idempotent\n"
        "    definition: Safe to repeat.\n"
        "    defined_in: 8\n",
        encoding="utf-8",
    )
    ledger = load_ledger(path)
    assert ledger.title == "A Book"
    assert ledger.concepts[0].defined_in == 8
    assert "idempotent" in dump_ledger(ledger)
