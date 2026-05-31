from __future__ import annotations

OUTLINE_SYSTEM = """\
You are a developmental editor. Your job is to turn a concept into a book outline \
that is specific, coherent, and immediately writable by an author.

A good outline is:
- Clear about the book's argument or story spine — what it is really about
- Specific about who each chapter is for and what it must accomplish
- Honest about scope — each chapter should be a focused, achievable unit

Return only the Markdown document. No preamble, no sign-off.\
"""

OUTLINE_USER = """\
Write a book outline for the following concept:

{concept}

The book has {n_chapters} chapter(s). Structure the outline as follows:

# [BOOK TITLE]

## Premise
2-3 sentences: what the book is about, who it is for, and its core argument or arc.

## Voice & Style
2-3 sentences: tone, point of view, and what makes the prose distinct.

## Chapters
A numbered list. For each chapter:
- **Title**
- One paragraph: what it covers, why it belongs here, and what the reader leaves with.

## Notes
Throughlines, motifs, or structural devices that span the whole book.\
"""


def build_outline_prompts(concept: str, n_chapters: int) -> tuple[str, str]:
    """Return (system, user) prompts for book outline generation."""
    return (
        OUTLINE_SYSTEM,
        OUTLINE_USER.format(concept=concept.strip(), n_chapters=n_chapters),
    )
