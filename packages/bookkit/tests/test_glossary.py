"""The generated glossary is part of the book, so it speaks the book's language."""

from __future__ import annotations

from bookkit.glossary import render_glossary
from content_kit_core.ledger import Concept, LedgerConfig


def test_the_glossary_speaks_the_book_s_language() -> None:
    """Every string the generator supplies follows `language`.

    A Spanish book whose glossary heading says "Glossary" and whose every
    entry says "also called" is the engine leaking into the book, which is the
    whole reason `_labels` exists.
    """
    ledger = LedgerConfig(
        title="Un libro",
        concepts=[
            Concept(
                term="despliegue",
                aka=["deploy"],
                definition="Poner un artefacto donde funcionará para usuarios reales.",
                defined_in=1,
            )
        ],
    )
    out = render_glossary(ledger, language="es")
    assert out.startswith("# Glosario")
    assert "Cada término que enseña este libro" in out
    assert "*(cap. 1)*" in out
    assert "— también llamado deploy" in out
    for english in ("Glossary", "also called", "(ch. "):
        assert english not in out


def test_an_unknown_language_falls_back_to_english() -> None:
    ledger = LedgerConfig(title="A book", concepts=[Concept(term="t", definition="d")])
    assert render_glossary(ledger, language="tlh").startswith("# Glossary")
