from __future__ import annotations

OUTLINE_SYSTEM = """\
You are a developmental editor. Your job is to turn a concept into a book outline \
that is specific, coherent, and immediately writable by an author.

A good outline is:
- Clear about the book's argument or story spine — what it is really about
- Specific about who each chapter is for and what it must accomplish
- Honest about scope — each chapter should be a focused, achievable unit

You also produce a STRUCTURED CANON (a "bible") so the book can be written with
strict continuity of plot and characters across every chapter.\
"""

OUTLINE_USER = """\
Write a book outline for the following concept:

{concept}

The book has {n_chapters} chapter(s).

Return TWO parts, in this order:

PART 1 — the prose outline, as Markdown:

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
Throughlines, motifs, or structural devices that span the whole book.

PART 2 — the structured canon, as a single fenced ```yaml code block matching this
schema exactly (fill it from the outline above; one beat per chapter):

```yaml
title: ""
logline: ""
themes: []
characters:
  - name: ""          # the character's name
    role: ""          # protagonist | antagonist | supporting | ...
    description: ""    # who they are
    voice: ""          # how they speak — kept consistent across the whole book
    arc: ""            # what changes for them
    status: alive      # alive | dead | departed | active | unknown
    first_appears: 1
beats:
  - chapter: 1
    summary: ""        # what happens in this chapter
    advances: []       # plot/character developments this chapter delivers
    state_changes: []  # canonical changes, e.g. "X leaves the city"
```

Output PART 1, then PART 2. Nothing else.\
"""


def build_outline_prompts(concept: str, n_chapters: int) -> tuple[str, str]:
    """Return (system, user) prompts for book outline + structured bible generation."""
    return (
        OUTLINE_SYSTEM,
        OUTLINE_USER.format(concept=concept.strip(), n_chapters=n_chapters),
    )
