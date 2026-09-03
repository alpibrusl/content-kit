"""Continuity checking — a linter for the canon (docs/continuity.md, docs/ledger.md).

Deterministic, dependency-free rules that catch the common ways a book drifts
from its own canon. Two canons, two rule sets, one ``Finding`` shape:

* **A story bible** (§5) — a dead or departed character reappearing, name
  drift, beats that don't line up with the chapters, broken series hand-offs.
* **A concept ledger** (§7) — the expository equivalent, where the thing that
  drifts is the teaching order rather than the plot: jargon used chapters
  before it is defined, a prerequisite that resolves to nothing, a term the
  ledger records and the book never says.

An optional LLM pass (driven from the CLI) complements the first set; this
module is the cheap, always-on first pass for both.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content_kit_core.ledger import LedgerConfig, name_pattern

from ._context import find_chapter_file
from .bible import BibleConfig
from .config import BookConfig
from .series import SeriesConfig

# Statuses that mean a character should no longer appear unless explicitly revived.
INACTIVE = {"dead", "departed", "gone", "deceased", "killed"}


@dataclass
class Finding:
    severity: str  # "error" | "warning"
    kind: str
    detail: str
    chapter: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "kind": self.kind,
            "detail": self.detail,
            "chapter": self.chapter,
        }


def _canonical_names(bible: BibleConfig) -> dict[str, str]:
    """Map lowercased name -> canonical name, for non-empty characters."""
    return {c.name.strip().lower(): c.name.strip() for c in bible.characters if c.name.strip()}


def _inactive_chapters(bible: BibleConfig) -> dict[str, tuple[int, str]]:
    """Per character, the chapter from which they are inactive and the status name.

    Built from the initial character status and from beat state_changes in order; a
    later change to an active status revives the character (clears the entry).
    """
    inactive: dict[str, tuple[int, str]] = {}
    for c in bible.characters:
        if c.name.strip() and c.status and c.status.lower() in INACTIVE:
            inactive[c.name] = (c.first_appears or 1, c.status.lower())
    for beat in sorted(bible.beats, key=lambda b: b.chapter):
        for sc in beat.state_changes:
            if not sc.character or not sc.set:
                continue
            status = str(sc.set.get("status", "")).lower()
            if status in INACTIVE:
                inactive[sc.character] = (beat.chapter, status)
            elif status and sc.character in inactive:
                inactive.pop(sc.character, None)
    return inactive


def check_book(
    bible: BibleConfig,
    config: BookConfig | None = None,
    book_dir: Path | None = None,
    scan_prose: bool = False,
) -> list[Finding]:
    """Run the deterministic book-level continuity rules."""
    findings: list[Finding] = []
    names = _canonical_names(bible)

    n_chapters = (
        len(config.chapters) if config else max((b.chapter for b in bible.beats), default=0)
    )

    # Duplicate beats for the same chapter.
    counts: dict[int, int] = {}
    for beat in bible.beats:
        counts[beat.chapter] = counts.get(beat.chapter, 0) + 1
    for chapter, count in sorted(counts.items()):
        if count > 1:
            findings.append(
                Finding(
                    "error", "duplicate-beat", f"{count} beats define chapter {chapter}", chapter
                )
            )

    # Beats out of range / missing beats (only when we know the chapter count).
    if n_chapters:
        for beat in bible.beats:
            if beat.chapter < 1 or beat.chapter > n_chapters:
                findings.append(
                    Finding(
                        "warning",
                        "beat-out-of-range",
                        f"beat for chapter {beat.chapter}, but the book has {n_chapters} chapters",
                        beat.chapter,
                    )
                )
        present = {b.chapter for b in bible.beats}
        for n in range(1, n_chapters + 1):
            if n not in present:
                findings.append(Finding("warning", "missing-beat", f"no beat for chapter {n}", n))

    # State changes referencing a character not in the bible (likely name drift).
    for beat in bible.beats:
        for sc in beat.state_changes:
            if sc.character and sc.character.strip() and sc.character.lower() not in names:
                close = difflib.get_close_matches(
                    sc.character.lower(), list(names), n=1, cutoff=0.8
                )
                hint = f" (did you mean '{names[close[0]]}'?)" if close else ""
                findings.append(
                    Finding(
                        "warning",
                        "unknown-character",
                        f"state_change references '{sc.character}' not in the bible{hint}",
                        beat.chapter,
                    )
                )

    # Dead/departed character reappearing in a later beat (or, with scan_prose, prose).
    flagged: set[tuple[str, int]] = set()
    for name, (since, status) in _inactive_chapters(bible).items():
        char = bible.character(name)
        # A mourned character is expected to be named after death (grief, memory),
        # so their later mentions are not revenant bugs.
        if char and char.mourned:
            continue
        canonical = names.get(name.lower(), name)
        aliases = [canonical, *(char.aka if char else [])]
        for beat in bible.beats:
            if beat.chapter <= since:
                continue
            haystack = " ".join([beat.summary, *beat.advances]).lower()
            if any(a and a.lower() in haystack for a in aliases):
                findings.append(
                    Finding(
                        "error",
                        "revenant",
                        f"{canonical} is {status} as of chapter {since} but appears in "
                        f"chapter {beat.chapter}'s beat",
                        beat.chapter,
                    )
                )
                flagged.add((canonical, beat.chapter))
        if scan_prose and book_dir:
            for beat in bible.beats:
                if beat.chapter <= since or (canonical, beat.chapter) in flagged:
                    continue
                path = find_chapter_file(book_dir, beat.chapter)
                if not path:
                    continue
                text = path.read_text(encoding="utf-8").lower()
                if any(a and a.lower() in text for a in aliases):
                    findings.append(
                        Finding(
                            "error",
                            "revenant",
                            f"{canonical} ({status} since chapter {since}) appears in "
                            f"chapter {beat.chapter}'s text",
                            beat.chapter,
                        )
                    )
    return findings


def check_series(series: SeriesConfig) -> list[Finding]:
    """Run the deterministic series-level continuity rules."""
    findings: list[Finding] = []
    dirs = {b.dir for b in series.books}
    for book in series.books:
        if book.opens_from and book.opens_from == book.dir:
            findings.append(
                Finding("error", "self-handoff", f"book '{book.dir}' opens_from itself")
            )
        elif book.opens_from and book.opens_from not in dirs:
            findings.append(
                Finding(
                    "error",
                    "broken-handoff",
                    f"book '{book.dir}' opens_from '{book.opens_from}', "
                    "which is not a book in the series",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Term continuity — the rules for an expository book (docs/ledger.md §3).
#
# A narrative book drifts by contradicting its own canon: a dead character
# turns up alive. An expository one drifts by contradicting its own *teaching
# order* — it uses a piece of jargon in chapter 3 that it does not define until
# chapter 9, and strands every reader who trusted it to introduce things before
# leaning on them. These rules make that a build failure rather than something
# a proofreader might notice on a good day.
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```.*?```", re.S)
_INLINE_CODE_RE = re.compile(r"`[^`]*`")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_SVG_RE = re.compile(r"<svg\b.*?</svg>", re.S | re.I)
_DIV_RE = re.compile(r"<div\b[^>]*>.*?</div>", re.S | re.I)
_PARA_SPLIT_RE = re.compile(r"\n\s*\n")
# "Chapter 7", "Chapters 6 and 7", "Chapters 3, 4 and 5", "Chapters 5-7",
# "Chapters 7 through 10" — every form these manuscripts actually use.
_SIGNPOST_RE = re.compile(r"chapters?\s+(\d+(?:\s*(?:,|and|&|to|through|-|–|—)\s*\d+)*)", re.I)
_RANGE_RE = re.compile(r"(\d+)\s*(?:-|–|—|to|through)\s*(\d+)")
# "Chapter 7 of the third book in this series" cites a sibling volume, not this one.
_CROSS_BOOK_RE = re.compile(r"^\s*of\b", re.I)


def strip_noise(text: str) -> str:
    """Remove the parts of a chapter that are not prose a reader reads.

    A term may legitimately appear early in any of these without having been
    introduced to anyone: code blocks and inline code are not sentences, a
    link's URL is not writing, and diagram markup is machinery. That last one
    is not hypothetical — an inline SVG's own attributes can contain a term's
    letters (the ``http`` inside ``xmlns="http://www.w3.org/2000/svg"`` reads
    as an early use of "HTTP") and produce a failure with no bad prose behind
    it, which is precisely the kind of false positive that teaches a team to
    stop believing the gate.
    """
    text = _FENCE_RE.sub(" ", text)
    text = _INLINE_CODE_RE.sub(" ", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _HTML_COMMENT_RE.sub(" ", text)
    text = _SVG_RE.sub(" ", text)
    text = _DIV_RE.sub(" ", text)
    return text


def _paragraphs(text: str) -> list[str]:
    return [p for p in _PARA_SPLIT_RE.split(text) if p.strip()]


def _signposted_chapters(paragraph: str) -> set[int]:
    """Every chapter number this paragraph points the reader at.

    Authors do not only write "Chapter 7". They write "Chapters 6 and 7",
    "Chapters 3, 4 and 5", "Chapters 5-7", "Chapters 7 through 10" — and a
    gate that recognises only
    the singular form rejects a properly signposted forward reference, which
    is the worst thing a linter can do: it punishes the writing it was built
    to encourage, and teaches the author that the escape hatch doesn't work.
    """
    found: set[int] = set()
    for match in _SIGNPOST_RE.finditer(paragraph):
        found |= _expand(match.group(1))
    return found


def _expand(span: str) -> set[int]:
    """The chapter numbers named by one signpost span, ranges included."""
    found: set[int] = set()
    for start, end in _RANGE_RE.findall(span):
        lo, hi = int(start), int(end)
        if lo <= hi:
            found.update(range(lo, hi + 1))
    found.update(int(n) for n in re.findall(r"\d+", span))
    return found


def _chapter_references(paragraph: str) -> list[tuple[int, str]]:
    """Every chapter this paragraph names, with the text that follows it.

    The trailing text is what separates "Chapter 7" from "Chapter 7 of the
    third book in this series" — the second is a citation of a sibling volume,
    whose chapter count is none of this book's business.
    """
    found: list[tuple[int, str]] = []
    for match in _SIGNPOST_RE.finditer(paragraph):
        tail = paragraph[match.end() : match.end() + 24]
        for number in sorted(_expand(match.group(1))):
            found.append((number, tail))
    return found


def _signposts(paragraph: str, chapter: int) -> bool:
    """Whether this paragraph tells the reader where the term is defined.

    "Containers (Chapter 7) package the program..." is good writing, not an
    error — the reader is told exactly where the definition lives. An
    *unsignposted* forward reference is the error, because that is the one that
    leaves a reader stranded.
    """
    return chapter in _signposted_chapters(paragraph)


def _first_use(names: list[str], prose: dict[int, list[str]]) -> tuple[int, str] | None:
    """The earliest chapter and paragraph in which any of ``names`` appears."""
    if not names:
        return None
    pattern = re.compile("|".join(name_pattern(n) for n in names), re.I)
    for number in sorted(prose):
        for para in prose[number]:
            if pattern.search(para):
                return number, para
    return None


def _dependency_cycles(ledger: LedgerConfig) -> list[list[str]]:
    """Every dependency cycle among concepts, each reported once.

    ``prerequisite-inversion`` catches a cycle whose members sit in different
    chapters, because one of the edges must then point backwards. A cycle
    entirely inside one chapter has no backwards edge and slips through, so it
    is worth finding directly.
    """
    edges = {c.term: [d for d in c.depends_on if d != c.term] for c in ledger.concepts}
    known = set(edges)
    cycles: list[list[str]] = []
    seen: set[frozenset[str]] = set()
    state: dict[str, int] = {}  # 0 = visiting, 1 = done

    def walk(term: str, path: list[str]) -> None:
        state[term] = 0
        for dep in edges.get(term, []):
            if dep not in known:
                continue  # reported by term-never-defined instead
            if state.get(dep) == 0:
                cycle = path[path.index(dep) :] + [dep]
                key = frozenset(cycle)
                if key not in seen:
                    seen.add(key)
                    cycles.append(cycle)
            elif dep not in state:
                walk(dep, [*path, dep])
        state[term] = 1

    for term in edges:
        if term not in state:
            walk(term, [term])
    return cycles


def check_terms(
    ledger: LedgerConfig,
    chapters: dict[int, str] | None = None,
    *,
    n_chapters: int | None = None,
    require_analogy: bool = False,
) -> list[Finding]:
    """Run the deterministic term rules for an expository book.

    ``chapters`` maps a chapter number to its raw Markdown. Omit it to check
    the ledger's internal consistency alone — useful while a book is still
    being outlined, when there is no prose to scan yet.

    ``require_analogy`` is off by default. An analogy is a tool for the ideas
    that need one, not a box every entry must fill, and a book with 150 terms
    would drown a useful gate in 120 reminders. Turn it on to audit how much
    of a ledger has actually been given the metaphor it promises.
    """
    findings: list[Finding] = []
    concepts = ledger.concepts
    by_term = {c.term: c for c in concepts}
    # Only a declared chapter count can bound a range. Inferring it from the
    # files on disk would flag a legitimate forward reference in a book that is
    # half drafted -- exactly when forward references are most common.
    total_chapters = n_chapters

    # --- one name, one owner -------------------------------------------------
    owner: dict[str, str] = {}
    for c in concepts:
        for name in c.names:
            key = name.strip().lower()
            if key in owner and owner[key] != c.term:
                findings.append(
                    Finding(
                        "error",
                        "term-defined-twice",
                        f"'{name}' is claimed by both '{owner[key]}' and '{c.term}'",
                    )
                )
            owner[key] = c.term

    # --- each concept is complete enough to teach and to print ---------------
    for c in concepts:
        if not c.definition.strip():
            findings.append(
                Finding(
                    "error",
                    "concept-missing-definition",
                    f"'{c.term}' has no definition — it would render as an empty "
                    "glossary entry, and there is nothing for the book to commit to",
                    c.defined_in or None,
                )
            )
        if require_analogy and not c.analogy.strip():
            findings.append(
                Finding(
                    "warning",
                    "concept-missing-analogy",
                    f"'{c.term}' commits to no analogy — the ledger's promise is one "
                    "definition and one metaphor per idea, so prose is free to invent "
                    "a different one each time it explains this",
                    c.defined_in or None,
                )
            )
        if isinstance(c.scan, list):
            known = {n.strip().lower() for n in c.names}
            for name in c.scan:
                if name.strip().lower() not in known:
                    findings.append(
                        Finding(
                            "error",
                            "scan-name-unknown",
                            f"'{c.term}' asks to scan for '{name}', which is neither its "
                            "term nor one of its aka names — so the rule scans for a "
                            "string the ledger never claims",
                            c.defined_in or None,
                        )
                    )
        if c.defined_in <= 0:
            findings.append(
                Finding(
                    "error",
                    "defined-in-missing",
                    f"'{c.term}' has no defined_in chapter — nothing is 'before' it, so "
                    "the used-before-defined rule silently never fires for this term",
                )
            )
        elif total_chapters and c.defined_in > total_chapters:
            findings.append(
                Finding(
                    "error",
                    "defined-in-out-of-range",
                    f"'{c.term}' is defined_in chapter {c.defined_in}, but the book has "
                    f"{total_chapters} chapters",
                    c.defined_in,
                )
            )

    # --- prerequisites resolve, point forwards, and terminate ----------------
    for c in concepts:
        for dep in c.depends_on:
            if dep == c.term:
                findings.append(
                    Finding(
                        "error",
                        "self-dependency",
                        f"'{c.term}' lists itself as a prerequisite",
                        c.defined_in or None,
                    )
                )
                continue
            target = by_term.get(dep)
            if target is None:
                findings.append(
                    Finding(
                        "error",
                        "term-never-defined",
                        f"'{c.term}' depends on '{dep}', which no concept defines",
                        c.defined_in or None,
                    )
                )
            elif target.defined_in > c.defined_in:
                findings.append(
                    Finding(
                        "error",
                        "prerequisite-inversion",
                        f"'{c.term}' (ch. {c.defined_in}) depends on '{dep}' "
                        f"(ch. {target.defined_in}) — the reading order cannot work",
                        c.defined_in or None,
                    )
                )
    for cycle in _dependency_cycles(ledger):
        findings.append(
            Finding(
                "error",
                "dependency-cycle",
                "prerequisites form a loop: " + " -> ".join(cycle),
            )
        )

    if chapters is None:
        return findings

    prose = {n: _paragraphs(strip_noise(text)) for n, text in chapters.items()}

    # --- the prose actually obeys the ledger ---------------------------------
    for c in concepts:
        # Orphan detection looks for EVERY name, including the ordinary-English
        # ones: a term whose only distinctive synonym is unused is not an orphan
        # if the book says "database" on every other page.
        if prose and _first_use(c.names, prose) is None:
            findings.append(
                Finding(
                    "warning",
                    "orphan-concept",
                    f"'{c.term}' is in the ledger but never used in the prose",
                    c.defined_in or None,
                )
            )
            continue

        # Used-before-defined, by contrast, looks only at the distinctive names,
        # so an ordinary word cannot produce a false failure that blocks a build.
        found = _first_use(c.scannable_names, prose)
        if found is None:
            continue
        number, para = found
        if number >= c.defined_in or _signposts(para, c.defined_in):
            continue
        findings.append(
            Finding(
                "error",
                "term-used-before-defined",
                f"'{c.term}' is used in ch. {number} but defined in ch. {c.defined_in} — "
                f"either move the definition, reword, or signpost it with an explicit "
                f'"Chapter {c.defined_in}"',
                number,
            )
        )

    # --- cross-references point at chapters that exist ----------------------
    # Inserting a chapter renumbers everything after it, and the references in
    # the prose do not move. The signpost escape hatch above then accepts a
    # number that is simply wrong, so this is also what keeps that hatch honest.
    if total_chapters:
        for number in sorted(prose):
            for para in prose[number]:
                for target, tail in _chapter_references(para):
                    if 1 <= target <= total_chapters or _CROSS_BOOK_RE.match(tail):
                        continue
                    findings.append(
                        Finding(
                            "error",
                            "chapter-reference-out-of-range",
                            f"chapter {number} points the reader at Chapter {target}, but the "
                            f"book has {total_chapters} chapters — renumbered, or a typo?",
                            number,
                        )
                    )

    # --- every chapter teaches something, unless it says it doesn't ---------
    defining = {c.defined_in for c in concepts}
    declared = set(ledger.teaches_no_terms)
    for number in sorted(prose):
        if number in defining or number in declared:
            continue
        findings.append(
            Finding(
                "warning",
                "chapter-defines-nothing",
                f"chapter {number} introduces no term the ledger records — "
                "deliberate, or is its vocabulary going unrecorded? Add it to "
                "teaches_no_terms to say the silence is on purpose.",
                number,
            )
        )
    for number in sorted(declared & defining):
        findings.append(
            Finding(
                "warning",
                "stale-teaches-no-terms",
                f"chapter {number} is listed in teaches_no_terms but does define a "
                "term now — drop it from the list",
                number,
            )
        )
    return findings
