"""The concept ledger — canonical, structured *teaching* data for a book.

The story bible in :mod:`content_kit_core.canon` is the canon of a narrative
book: who exists, what happened, in what order. A ``glossary.yaml`` is the
equivalent canon for an expository one — every piece of jargon the book
teaches, the ONE definition it commits to, the ONE analogy it uses for that
idea throughout, the chapter that introduces it, and the terms a reader must
already have met for it to make sense.

Same discipline as the bible, for the same reason: a definition that lives in
one committed file cannot drift from itself, and a reading order written down
as data can be checked by a machine instead of noticed by a proofreader.

Two things are derived from a ledger and neither is committed: the generated
glossary (``bookkit glossary``) and the continuity gate (``bookkit check
terms``). Core owns the model and the matching rules; the rules that read a
manuscript live in bookkit, which is the tier that knows what a chapter is.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class Concept(BaseModel):
    """One term the book teaches, and everything the book commits to about it."""

    term: str
    """The canonical name — the spelling the glossary prints and every rule reports."""

    definition: str = ""
    """The one plain-language definition, used verbatim in the generated glossary."""

    defined_in: int = 0
    """The chapter that introduces the term. The gate reads prose in chapter
    order and fails a use that lands before this one without a signpost."""

    aka: list[str] = []
    """Synonyms and near-misses a reader will meet elsewhere. Claimed by this
    concept, so no other concept may also claim them."""

    analogy: str = ""
    """The metaphor the book commits to and never contradicts. Optional in the
    model, reported by ``concept-missing-analogy`` when absent, because a
    ledger's whole point is that there is exactly one of these per idea."""

    depends_on: list[str] = []
    """Terms that must already be defined for this one to make sense. Drives
    both ``term-never-defined`` and ``prerequisite-inversion``."""

    scan: bool | list[str] | None = None
    """Which of this concept's names the prose gate hunts for.

    ``None`` (the default) scans the names distinctive enough to be safe;
    ``true`` adds the canonical term to that set; ``false`` opts the concept
    out of prose scanning entirely; a list names exactly what to scan and
    nothing else. See :attr:`scannable_names`."""

    @property
    def names(self) -> list[str]:
        """Every string that refers to this concept."""
        return [self.term, *self.aka]

    @property
    def scannable_names(self) -> list[str]:
        """The names distinctive enough to hunt for in prose.

        Scanning is deliberately conservative. Ordinary English words — "test",
        "plan", "state", "image", "fake" — appear constantly in prose that is
        not about the concept at all, and flagging them would make the gate
        noisy enough that people would learn to ignore it, which is worse than
        not having a gate.

        So a name is scanned only if it is multi-word, hyphenated, or an
        acronym — all three are shapes ordinary prose does not produce by
        accident. A single word that is genuinely distinctive jargon
        ("idempotent", "stateless") opts in with ``scan: true``, which adds the
        canonical term — but NOT its synonyms, since those are exactly where
        the ordinary English creeps in ("login" for authentication,
        "permissions" for authorization).

        That default is a heuristic, and a heuristic has exceptions in both
        directions. "sanity check" is a perfectly good alias for a
        known-answer test *and* an ordinary English verb, so scanning it finds
        prose that has nothing to do with the concept. ``scan: false`` would
        answer that by giving up the check on the distinctive name too, which
        is why a list is allowed: ``scan: ["known-answer test"]`` keeps the
        rule that earns its place and drops the one that doesn't.
        """
        if self.scan is False:
            return []
        if isinstance(self.scan, list):
            return list(self.scan)
        names = [n for n in self.names if " " in n or "-" in n or (n.isupper() and len(n) > 1)]
        if self.scan is True and self.term not in names:
            names.append(self.term)
        return names


class LedgerConfig(BaseModel):
    """A whole ``glossary.yaml``: what kind of book this is, and its concepts."""

    kind: str = "technical"
    """The genre this ledger belongs to. Reserved for genre-aware rule sets;
    every rule shipped today applies to any expository book."""

    title: str = ""
    concepts: list[Concept] = []

    teaches_no_terms: list[int] = []
    """Chapters that deliberately introduce no term this ledger records.

    A closing checklist chapter and an afterword recap the book rather than
    extend its vocabulary, and saying so once as data is better than a linter
    asking the same question on every run forever. The rule that reads this
    also flags a stale entry, so the declaration cannot quietly outlive the
    fact."""

    def concept(self, name: str) -> Concept | None:
        """Look up a concept by canonical name or alias, case-insensitively."""
        key = name.strip().lower()
        for c in self.concepts:
            if c.term.strip().lower() == key or key in {a.strip().lower() for a in c.aka}:
                return c
        return None


def load_ledger(path: Any) -> LedgerConfig:
    """Load and validate a glossary.yaml into a LedgerConfig."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return LedgerConfig.model_validate(raw)


def dump_ledger(ledger: LedgerConfig) -> str:
    """Serialize a LedgerConfig back to YAML (empties dropped)."""
    data = ledger.model_dump(exclude_defaults=True)
    return yaml.dump(data, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------------------
# Matching a term in prose
#
# Lives here, next to the model, because the same inflection rules have to be
# used by every consumer of a ledger. A gate that matches "dependency" but not
# "dependencies" is not a stricter gate — it is a gate with holes in it, and
# the holes are invisible, which is the bad kind.
# ---------------------------------------------------------------------------

_SPLIT_RE = re.compile(r"[\s\-]+")
_CONSONANT_Y_RE = re.compile(r"[^aeiou]y$", re.I)
_SIBILANT_RE = re.compile(r"(?:s|x|z|ch|sh)$", re.I)


def _inflect(word: str) -> str:
    """A regex matching one word and its regular English plural.

    Only the *last* word of a term is inflected — "environment variable"
    pluralizes as "environment variables", never "environments variable".
    """
    if _CONSONANT_Y_RE.search(word):
        # dependency -> dependencies, retry -> retries, anomaly -> anomalies
        return re.escape(word[:-1]) + r"(?:y|ies)"
    if word.lower().endswith("is") and len(word) > 3:
        # analysis -> analyses, hypothesis -> hypotheses, basis -> bases
        return re.escape(word[:-2]) + r"(?:is|es)"
    escaped = re.escape(word)
    if _SIBILANT_RE.search(word):
        # bias -> biases, index -> indexes, batch -> batches
        return escaped + r"(?:es)?"
    return escaped + r"(?:e?s)?"


def name_pattern(name: str) -> str:
    """Match a term in prose, tolerating the ways real writing spells it.

    Three tolerances, each of which was a silent hole in the gate before it
    existed — and a hole in a linter is worse than a missing linter, because
    the green tick is read as evidence:

    * **Plurals.** Without this, "environment variable" fails to match the
      phrase "environment variables", because the trailing word boundary lands
      inside the plural. Irregular-but-common forms count: a gate that misses
      "dependencies" is not checking the word "dependency" at all.
    * **Separators.** "trade-off", "trade off" and "tradeoff" are the same
      term. A hyphenated term matches all three; a space-separated one requires
      *some* separator, since collapsing "objective function" into one word is
      not something a writer does by accident.
    * **Line breaks.** The separator class includes newlines, so a multi-word
      term still matches when a hard-wrapped manuscript happens to break the
      line in the middle of it.
    """
    parts = [p for p in _SPLIT_RE.split(name.strip()) if p]
    if not parts:
        return r"(?!)"  # never matches, rather than matching everything
    # A hyphenated term may also be written closed up ("tradeoff"); a
    # space-separated one may not.
    separator = r"[\s\-]*" if "-" in name else r"[\s\-]+"
    body = separator.join([*(re.escape(p) for p in parts[:-1]), _inflect(parts[-1])])
    return rf"\b{body}\b"
