# Design: The concept ledger — teaching coherence in an expository book

`continuity.md` is about a book that has characters. This one is about a book
that has *jargon*.

## 1. The problem

A narrative book drifts by contradicting its own canon: a character who died in
chapter 4 orders coffee in chapter 9. An expository book has an equivalent
failure, and it is both more common and easier to miss, because nothing in the
text looks wrong.

It uses a term before it teaches it.

A reader who meets "idempotent" in chapter 3, in a sentence that assumes they
know it, has two options: stop and look it up elsewhere, or keep going with a
hole in the argument. Both are the book's fault. And the failure is invisible to
the author, who knew what the word meant the whole time — which makes it exactly
the class of problem worth handing to a machine.

Two related failures come with it:

- **Two definitions of one idea.** A term defined in chapter 3 and re-defined,
  slightly differently, in chapter 11. The reader cannot tell which one the book
  means, and neither, by then, can the author.
- **A metaphor that shifts.** A book explains a queue as a "conveyor belt" once
  and a "waiting room" later. Each is fine alone; together they teach nothing,
  because the reader is now maintaining two mental models of one thing.

## 2. Canon as data

A `glossary.yaml` is to an expository book what `bible.yaml` is to a narrative
one: the committed, checkable statement of what the book claims.

```yaml
kind: technical
title: "Prompt to Production"

concepts:
  - term: "idempotent"
    aka: ["idempotence", "idempotency"]
    definition: >-
      Safe to repeat: running it twice leaves you in the same place as running
      it once.
    analogy: "A light switch labelled ON — pressing it again does not make the room brighter."
    depends_on: ["declarative"]
    defined_in: 8
    scan: true
```

| field | |
|---|---|
| `term` | the canonical name; what the glossary prints and every rule reports |
| `aka` | synonyms and near-misses a reader will meet elsewhere |
| `definition` | the ONE definition, used verbatim in the generated glossary |
| `analogy` | the ONE metaphor the book commits to and never contradicts |
| `depends_on` | terms that must already be defined for this one to make sense |
| `defined_in` | the chapter that introduces it |
| `scan` | which names the prose gate hunts for — see §4 |

A ledger also carries one book-level field:

```yaml
teaches_no_terms: [15, 16]   # the closing checklist and the afterword
```

Some chapters recap the book's vocabulary rather than extend it. Saying so once,
as data, is better than a linter asking the same question on every run forever —
and `stale-teaches-no-terms` fires if such a chapter later does define something,
so the declaration cannot quietly outlive the fact.

The model lives in `content_kit_core.ledger`, next to the bible, because it is
canon and core owns canon. The rules that read a manuscript live in bookkit,
which is the tier that knows what a chapter is.

## 3. `bookkit check terms` — the guard

Same envelope and exit codes as `check continuity`: `0` clean, `8`
PRECONDITION_FAILED. Deterministic, no API, always cheap enough to run in CI on
every push.

| rule | severity | |
|---|---|---|
| `term-used-before-defined` | error | a term appears in prose before its chapter, with no signpost |
| `term-never-defined` | error | a `depends_on` entry no concept defines |
| `term-defined-twice` | error | two concepts claim the same name |
| `prerequisite-inversion` | error | A depends on B, but A is defined first |
| `dependency-cycle` | error | prerequisites form a loop |
| `self-dependency` | error | a term lists itself as a prerequisite |
| `concept-missing-definition` | error | nothing for the book to commit to, and an empty glossary entry |
| `defined-in-missing` | error | no chapter, so the used-before-defined rule silently never fires |
| `defined-in-out-of-range` | error | `defined_in` past the end of the book |
| `scan-name-unknown` | error | `scan:` lists a name the concept doesn't claim |
| `chapter-reference-out-of-range` | error | the prose points at a chapter the book does not have |
| `orphan-concept` | warning | in the ledger, never used in the prose |
| `chapter-defines-nothing` | warning | a chapter whose vocabulary the ledger never records, and which hasn't declared that |
| `stale-teaches-no-terms` | warning | a chapter declared term-free that now defines one |
| `concept-missing-analogy` | warning | opt-in (`--require-analogy`); see §5 |

```
  ch 1  ERROR   term-used-before-defined: 'trade-off' is used in ch. 1 but
                defined in ch. 5 — either move the definition, reword, or
                signpost it with an explicit "Chapter 5"
  ch16  WARNING chapter-defines-nothing: chapter 16 introduces no term the
                ledger records — deliberate, or is its vocabulary going
                unrecorded?

checked 151 concepts against 17 chapters: 1 error(s), 1 warning(s)
```

Inserting a chapter renumbers everything after it while the references in the
prose stay put, so `chapter-reference-out-of-range` is also what keeps the
signpost hatch honest: without it the hatch will happily accept a number that is
simply wrong. It needs a declared chapter count (`book.yaml`) rather than
inferring one from the files on disk — a half-drafted book is exactly where a
forward reference to an unwritten chapter is legitimate. A citation of a sibling
volume ("Chapter 7 of the third book in this series") is left alone.

`--ledger-only` skips the prose entirely and checks the ledger's own
consistency, which is what you want while a book is still an outline.
`--strict` makes warnings fail too.

## 4. Why the gate is deliberately quiet

A linter nobody trusts is worse than no linter, because a green tick gets read
as evidence. Three design choices exist only to keep the false-positive rate
near zero.

**Only distinctive names are scanned.** Ordinary English words — "test", "plan",
"state", "image" — appear constantly in prose that is not about the concept, and
flagging them would train everyone to ignore the gate. A name is scanned only if
it is multi-word, hyphenated, or an acronym: three shapes ordinary prose does not
produce by accident. A single word that is unambiguous jargon opts in with
`scan: true` — which adds the canonical term but **not** its synonyms, since
those are exactly where the ordinary English creeps in ("login" for
authentication, "permissions" for authorization).

That default is a heuristic, and heuristics have exceptions both ways.
"sanity check" is a good alias for a known-answer test *and* an ordinary English
verb. `scan: false` would answer that by giving up the check on the distinctive
name too, so `scan:` also takes a list:

```yaml
  - term: "known-answer test"
    aka: ["sanity check"]
    scan: ["known-answer test"]     # keep the rule that earns its place
```

**Signposted forward references are allowed.** "Containers (Chapter 7) package
the program…" is good writing, not an error — the reader is told exactly where
the definition lives. An *unsignposted* forward reference is the error, because
that is the one that strands a reader. The signpost is recognised in the forms
authors actually write: `Chapter 7`, `Chapters 6 and 7`, `Chapters 3, 4 and 5`,
`Chapters 5-7`. A gate that accepts only the singular rejects properly
signposted prose, which teaches the author that the escape hatch doesn't work.

**Only prose is scanned.** Code fences, inline code, link URLs, HTML comments
and diagram markup are stripped first. This is not hypothetical: an inline SVG's
own attributes can contain a term's letters — the `http` inside
`xmlns="http://www.w3.org/2000/svg"` reads as an early use of "HTTP" — and
produce a failure with no bad prose behind it.

**Matching tolerates how people actually write.** A gate that matches
"dependency" but not "dependencies" is not a stricter gate; it is a gate with
invisible holes. `content_kit_core.ledger.name_pattern` handles regular and
common irregular plurals (`dependency/dependencies`, `analysis/analyses`,
`bias/biases`), the three spellings of a hyphenated term
(`trade-off`/`trade off`/`tradeoff`), and line breaks inside a multi-word term.

## 5. `--require-analogy` is opt-in

The ledger's promise is one definition *and* one metaphor per idea, so a missing
analogy is worth being able to see. It is off by default anyway: an analogy is a
tool for the ideas that need one, not a box every entry must fill, and a book
with 150 terms would drown a useful gate in 120 reminders. Turn it on to audit
how much of a ledger has actually been given the metaphor it promises.

## 6. `bookkit glossary` — the back matter

The ledger is source; `GLOSSARY.md` is a build artifact, generated and never
committed. Hand-editing it would create exactly the drift a ledger exists to
prevent.

```bash
bookkit glossary -b .        # → GLOSSARY.md, a Markdown definition list
```

It drops straight into `back_matter` in `book.yaml` and renders through the same
path as any other matter file:

```yaml
back_matter:
  - { file: GLOSSARY.md, title: "Glossary" }
```

## 7. Provenance

Both commands began as `scripts/` inside `alpibrusl/prompt-to-production` and
were duplicated, byte for byte, into three sibling books — which is how the
need for them upstream got demonstrated rather than argued. They implement
content-kit issues #9 (a genre-aware canon with a `Concept` model), #10
(genre-aware continuity rules) and #11 (a generated glossary as back matter).

Two findings from writing those books are baked in above rather than left as
lessons: forward references need a signpost escape hatch, and prose scanning
must be conservative about ordinary English or the gate becomes noise.
