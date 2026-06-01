"""Heuristic dialogue attribution for full-cast audiobooks.

Single-narrator narration is the safe default; this module is what turns a book
into a *cast* reading. It splits chapter prose into an ordered list of
``(speaker, text)`` segments: narration is the narrator, and quoted or dash-led
dialogue is attributed to a character from the bible **only when an attribution
cue names one**. Attribution is deliberately conservative — when it cannot
justify a speaker (no cue, or an ambiguous one), it leaves the line with the
narrator rather than guess. A wrong voice is more jarring than a narrated line.

Two dialogue conventions are recognized:

* **Quoted** (English &c.): ``"Run," said Mara.`` — quoted spans are dialogue,
  everything outside the quotes (including the ``said Mara`` tag) is narration.
* **Dash-led** (Spanish/French): ``—Corre —dijo Mara—. Y corrió.`` — the dash
  opens speech; segments between dashes alternate speech / narration.

The speaker for a dialogue paragraph is resolved from a *speech-verb cue*
(``said``/``dijo``/``dit`` …) sitting next to a known character name or alias.
"""

from __future__ import annotations

import re

from .bible import BibleConfig

# Verbs of speech across the languages bookkit's sample saga uses. A name next to
# one of these is treated as an attribution ("said Mara", "—dijo Vera").
_SPEECH_VERBS = {
    # English
    "said",
    "says",
    "asked",
    "asks",
    "replied",
    "answered",
    "whispered",
    "shouted",
    "murmured",
    "added",
    "cried",
    "exclaimed",
    "muttered",
    "called",
    # Spanish
    "dijo",
    "decía",
    "preguntó",
    "respondió",
    "contestó",
    "susurró",
    "gritó",
    "murmuró",
    "añadió",
    "exclamó",
    "repuso",
    "repitió",
    "insistió",
    # French
    "dit",
    "demanda",
    "répondit",
    "murmura",
    "cria",
    "ajouta",
    "souffla",
}
_VERB_RE = re.compile(r"\b(" + "|".join(sorted(_SPEECH_VERBS, key=len, reverse=True)) + r")\b")

# Quote pairs: straight, French guillemets, curly doubles, curly singles.
_QUOTE_SPAN_RE = re.compile(r"\"[^\"]+\"|«[^»]+»|“[^”]+”|‘[^’]+’")
_DASH_START_RE = re.compile(r"^\s*[—–]")
_DASH_SPLIT_RE = re.compile(r"\s*[—–]\s*")
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


class Matcher:
    """Maps a word found in prose to a canonical bible character name.

    Indexes each character by full name, every alias, and — when unambiguous —
    the first token of the name (so "Vera" resolves to "VERA QUINTELA"). Tokens
    shared by more than one character are dropped, so an ambiguous mention never
    produces a confident (wrong) attribution.
    """

    def __init__(self, bible: BibleConfig | None) -> None:
        token_to_names: dict[str, set[str]] = {}

        def add(token: str, canon: str) -> None:
            key = token.strip().lower()
            if key:
                token_to_names.setdefault(key, set()).add(canon)

        for character in bible.characters if bible else []:
            canon = character.name.strip().upper()
            if not canon:
                continue
            add(character.name, canon)
            for alias in character.aka:
                add(alias, canon)
            first = character.name.strip().split()
            if first:
                add(first[0], canon)

        # Keep only tokens that point at exactly one character.
        self._token: dict[str, str] = {
            tok: next(iter(names)) for tok, names in token_to_names.items() if len(names) == 1
        }

    def find(self, text: str) -> str | None:
        """Return the single character named in ``text``, or None if 0 or >1."""
        found = self.find_all(text)
        return next(iter(found)) if len(found) == 1 else None

    def find_all(self, text: str) -> set[str]:
        """Return every distinct character named anywhere in ``text``."""
        return {self._token[w.lower()] for w in _WORD_RE.findall(text) if w.lower() in self._token}

    def attribution_speaker(self, text: str) -> str | None:
        """Resolve a speaker only from a *cued* attribution within ``text``.

        Requires a known character name within three words of a speech verb,
        e.g. "said Mara" / "Mara asked" / "dijo Vera". The window is intentionally
        narrow so an unrelated name elsewhere in the line (another character
        merely mentioned) does not produce a wrong attribution. Returns None when
        no cue resolves to exactly one character.
        """
        tokens = _WORD_RE.findall(text)
        candidates: set[str] = set()
        for i, word in enumerate(tokens):
            if word.lower() not in _SPEECH_VERBS:
                continue
            # The speaker is the name *closest* to the verb (e.g. "said Mara"),
            # so a name two words away in the next clause never wins over it.
            nearest = self._nearest_name(tokens, i, reach=3)
            if nearest:
                candidates.add(nearest)
        return next(iter(candidates)) if len(candidates) == 1 else None

    def _nearest_name(self, tokens: list[str], i: int, *, reach: int) -> str | None:
        for d in range(1, reach + 1):
            for j in (i + d, i - d):
                if 0 <= j < len(tokens):
                    canon = self._token.get(tokens[j].lower())
                    if canon:
                        return canon
        return None


def _strip_quotes(span: str) -> str:
    return span[1:-1].strip()


def attribute_paragraph(paragraph: str, matcher: Matcher, narrator: str) -> list[tuple[str, str]]:
    """Split one paragraph into ordered ``(speaker, text)`` segments.

    Non-dialogue paragraphs return a single narrator segment. Dialogue paragraphs
    return interleaved narrator/character segments, preserving reading order.
    """
    paragraph = paragraph.strip()
    if not paragraph:
        return []

    if _DASH_START_RE.match(paragraph):
        return _attribute_dash(paragraph, matcher, narrator)
    if _QUOTE_SPAN_RE.search(paragraph):
        return _attribute_quoted(paragraph, matcher, narrator)
    return [(narrator, paragraph)]


def _attribute_quoted(paragraph: str, matcher: Matcher, narrator: str) -> list[tuple[str, str]]:
    speaker = matcher.attribution_speaker(paragraph) or narrator
    segments: list[tuple[str, str]] = []
    pos = 0
    for m in _QUOTE_SPAN_RE.finditer(paragraph):
        before = paragraph[pos : m.start()].strip()
        if before:
            segments.append((narrator, before))
        quoted = _strip_quotes(m.group(0))
        if quoted:
            segments.append((speaker, quoted))
        pos = m.end()
    tail = paragraph[pos:].strip()
    if tail:
        segments.append((narrator, tail))
    return segments or [(narrator, paragraph)]


def _attribute_dash(paragraph: str, matcher: Matcher, narrator: str) -> list[tuple[str, str]]:
    # Speaker is resolved from the whole paragraph's attribution cues.
    speaker = matcher.attribution_speaker(paragraph) or narrator
    parts = [p.strip() for p in _DASH_SPLIT_RE.split(paragraph)]
    # split() yields a leading empty element because the paragraph starts with a dash.
    parts = parts[1:] if parts and parts[0] == "" else parts
    segments: list[tuple[str, str]] = []
    for i, part in enumerate(parts):
        if not part:
            continue
        # Odd-positioned (0, 2, …) parts are speech; interleaved parts are
        # narration/attribution. A narration part that is *only* a speech tag
        # (e.g. "dijo Vera") is dropped — the cast already conveys who spoke.
        if i % 2 == 0:
            segments.append((speaker, part))
        elif not (_VERB_RE.search(part) and matcher.find(part)):
            segments.append((narrator, part))
    return segments or [(narrator, paragraph)]


def attribute(text: str, bible: BibleConfig | None, narrator: str) -> list[tuple[str, str]]:
    """Attribute a whole chapter's speech text to ``(speaker, text)`` segments.

    ``text`` is the markdown-flattened speech for a chapter (paragraphs separated
    by blank lines). With no bible (or no resolvable cues) every segment is the
    narrator, i.e. it degrades exactly to single-narrator narration.
    """
    matcher = Matcher(bible)
    segments: list[tuple[str, str]] = []
    for paragraph in text.split("\n\n"):
        segments.extend(attribute_paragraph(paragraph, matcher, narrator))
    return segments
