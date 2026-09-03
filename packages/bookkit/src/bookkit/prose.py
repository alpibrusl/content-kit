"""Prose style rules — the house voice, as far as a machine can check it.

``continuity.py`` checks what the book *claims* (its canon). This module checks
how it *sounds*, which is a smaller and much more cautious job: almost nothing
about voice is mechanical, so only the handful of things that genuinely are
live here. Everything else belongs in a style guide a human reads.

Findings are warnings, never errors. A style gate that can block a build will
eventually block one for a sentence that was right, and then it gets disabled.
"""

from __future__ import annotations

import re

from .continuity import Finding

# Spans where prose rules must not look: a code listing and a diagram are not
# sentences, and neither is a link target.
_PROTECTED = [
    re.compile(r"```.*?```", re.DOTALL),
    re.compile(r"<svg\b.*?</svg>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<!--.*?-->", re.DOTALL),
    re.compile(r"`[^`\n]*`"),
    re.compile(r"\]\([^)]*\)"),
]

_COMMA_BECAUSE_RE = re.compile(r",(\s+)because\b")
_SENTENCE_END_RE = re.compile(r"[.!?]\s")

# A negated main clause is the classic case where the comma carries meaning:
# "He didn't leave, because he was angry" says something different without it.
_NEGATION_RE = re.compile(
    r"\b(not|n't|never|no|none|nothing|nobody|nowhere|rarely|hardly|scarcely|seldom|cannot)\b",
    re.IGNORECASE,
)
# "..., because it is." — an elliptical afterthought, where the comma is the pause.
_ELLIPTICAL_RE = re.compile(
    r",\s+because\s+\w+\s+(?:is|are|was|were|does|do|did|has|have|can|will)\s*[.,;—]"
)
# An em dash already opened an aside; a second break there is the author's rhythm.
_TRAILING_DASH_RE = re.compile(r"—[^—]{0,60}$")

# "not because X, but because Y" and "because X or because Y" are correlatives:
# the repetition is the structure of the sentence, not a stumble. Only an
# unpaired second "because" is worth reporting.
_REPEATED_BECAUSE_RE = re.compile(
    r"\bbecause\b(?P<between>[^.!?]{0,120}?)\bbecause\b", re.IGNORECASE
)
# Repeating "because" is usually deliberate: correlatives ("not because X, but
# because Y") and parallel list items ("a file that works because..., a step
# that only works because...") both read fine. Only one shape reliably trips a
# reader -- a because-clause whose predicate is itself "is not because" -- so
# that is the only one reported.
_STUMBLE_RE = re.compile(r"\b(?:is|was|are|were|am)\s+not\s*$", re.IGNORECASE)


def _protected_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for pattern in _PROTECTED:
        spans.extend((m.start(), m.end()) for m in pattern.finditer(text))
    return spans


def _in_protected(index: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= index < end for start, end in spans)


def _preceding_clause(text: str, index: int) -> str:
    """The main clause running up to ``index``, whitespace normalized."""
    head = text[max(0, index - 400) : index]
    last_end = 0
    for match in _SENTENCE_END_RE.finditer(head):
        last_end = match.end()
    return " ".join(head[last_end:].split())


def comma_before_because_is_wrong(text: str, index: int) -> bool:
    """Whether the comma at ``index`` precedes a *restrictive* because-clause.

    English takes no comma when the because-clause gives the essential reason:
    "worth knowing by name because it is the answer." A comma belongs there only
    when the clause is an afterthought, or when the main clause is negative and
    the comma is what keeps the sentence from meaning its opposite.

    Deliberately conservative — it answers True only for the plain restrictive
    case, and stays quiet on everything a careful writer might have meant.
    """
    clause = _preceding_clause(text, index)
    if _NEGATION_RE.search(clause):
        return False
    if _TRAILING_DASH_RE.search(clause):
        return False
    return not _ELLIPTICAL_RE.match(text[index : index + 80])


def fix_commas(text: str) -> tuple[str, int]:
    """Drop the comma before a restrictive because-clause. Returns (text, count)."""
    spans = _protected_spans(text)
    out: list[str] = []
    cursor = fixed = 0
    for match in _COMMA_BECAUSE_RE.finditer(text):
        if _in_protected(match.start(), spans):
            continue
        if not comma_before_because_is_wrong(text, match.start()):
            continue
        out.append(text[cursor : match.start()])
        out.append(match.group(1))  # keep the original whitespace, drop the comma
        cursor = match.end() - len("because")
        fixed += 1
    out.append(text[cursor:])
    return "".join(out), fixed


def check_prose(chapters: dict[int, str]) -> list[Finding]:
    """Run the house-style rules over each chapter's Markdown."""
    findings: list[Finding] = []
    for number in sorted(chapters):
        text = chapters[number]
        spans = _protected_spans(text)

        for match in _COMMA_BECAUSE_RE.finditer(text):
            if _in_protected(match.start(), spans):
                continue
            if not comma_before_because_is_wrong(text, match.start()):
                continue
            clause = _preceding_clause(text, match.start())
            findings.append(
                Finding(
                    "warning",
                    "comma-before-because",
                    f'restrictive because-clause takes no comma: "...{clause[-60:]}[,] because..."',
                    number,
                )
            )

        for match in _REPEATED_BECAUSE_RE.finditer(text):
            if _in_protected(match.start(), spans):
                continue
            if not _STUMBLE_RE.search(" ".join(match.group("between").split())):
                continue
            findings.append(
                Finding(
                    "warning",
                    "repeated-because",
                    f'"because ... is not because" is hard to follow: '
                    f'"...{" ".join(match.group(0).split())}..."',
                    number,
                )
            )
    return findings
