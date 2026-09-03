"""Generate a book's glossary from its concept ledger.

The ledger is source; the glossary is a build artifact. Hand-editing the
generated file would create exactly the drift a ledger exists to prevent, which
is why a book keeps ``GLOSSARY.md`` out of source control and rebuilds it.

The output is a Markdown definition list, so it drops straight into
``back_matter`` in ``book.yaml`` and renders through the same path as any other
matter file.
"""

from __future__ import annotations

from content_kit_core.ledger import Concept, LedgerConfig


def _flatten(text: str) -> str:
    """Collapse the folded YAML scalars a ledger is written in to one line."""
    return " ".join(text.split())


def render_glossary(
    ledger: LedgerConfig,
    *,
    title: str = "Glossary",
    intro: str | None = None,
) -> str:
    """Render a ledger as the book's back-matter glossary, sorted by term."""
    concepts: list[Concept] = sorted(ledger.concepts, key=lambda c: c.term.lower())
    if intro is None:
        intro = (
            "Every term this book teaches, with the definition it commits to.\n"
            "The chapter number is where the term is introduced."
        )

    lines = [f"# {title}", "", intro, ""]
    for c in concepts:
        entry = f"**{c.term}**"
        if c.defined_in:
            entry += f" *(ch. {c.defined_in})*"
        if c.aka:
            entry += f" — also called {', '.join(c.aka)}"
        lines.append(entry)
        lines.append("")
        lines.append(f": {_flatten(c.definition)}")
        if c.analogy:
            lines.append(f"  *{_flatten(c.analogy)}*")
        lines.append("")
    return "\n".join(lines)
