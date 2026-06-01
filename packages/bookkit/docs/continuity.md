# Design: Continuity — plot & character coherence across chapters and books

> **Resumen (ES):** Este documento diseña cómo `bookkit` garantiza continuidad de
> trama y personajes — dentro de un libro (capítulos correlacionados) y entre
> varios libros de una misma serie/colección. Cubre las cuatro piezas acordadas:
> **(A)** un *bible* estructurado como canon, **(B)** contexto acumulado
> ("en capítulos anteriores…"), **(C)** *bible* de serie para libros
> correlacionados, y **(D)** el comando `check continuity`. Es un documento de
> diseño para revisar **antes** de implementar.

**Status:** proposal, pre-implementation. Nothing here is built yet.

---

## 1. The problem

An LLM does not guarantee continuity on its own. If you generate chapter 7 by
handing the model only an outline, it will happily contradict chapter 3 — kill a
character who is alive, change someone's accent, or forget a promise made two
chapters ago. Across *multiple* books the drift is worse.

Continuity is not a model capability; it is an **information-flow discipline**. We
ensure it the way `noted` did — by keeping a canonical *bible* in context — but we
make that discipline first-class, structured, and automatable. Three mechanisms
produce continuity, and a fourth verifies it:

| | Mechanism | Guarantees |
|---|---|---|
| **A** | Structured **bible** (canon), always in context | Characters, world, timeline never invented ad hoc |
| **B** | **Running recap** of prior chapters fed into the next | A chapter is written *knowing what already happened* |
| **C** | **Series bible** + inherited state across books | Book 2 opens from Book 1's ending canon |
| **D** | `check continuity` — automated guard | Contradictions are caught, not shipped |

The design principle is unchanged from the rest of `bookkit`: **the bible is plain
text, committed, reproducible and auditable.** Continuity lives in source control,
not in a model's memory.

---

## 2. (A) The bible — canon as data

A new file per book, `bible.yaml`, is the single source of truth. It is injected
(in full, or as a relevant slice — see §6) into *every* generation: `write
outline`, `write chapter`, and `check continuity`.

```yaml
# bible.yaml
title: "The Compliance Engine"
logline: "A compliance officer discovers the AI she audits is rewriting the rules."
themes: ["control vs. agency", "bureaucracy as horror"]

world:
  - id: engine
    fact: "The Engine is an AI deployed across the city's logistics; it is polite, literal, and never off."
    tags: [premise]
  - id: city
    fact: "Set in a rain-grey Düsseldorf analogue, near-future."
    tags: [setting]

timeline:
  - when: "T-0"
    event: "The Engine goes live."
  - when: "T+3 days"
    event: "First anomaly logged."

characters:
  - name: "MARA"
    aka: ["the Inspector"]
    role: protagonist
    description: "Mid-30s compliance officer. Precise, tired, quietly rebellious."
    voice: "Clipped, formal, dry. Speaks in short declaratives. Never swears."
    relationships:
      - with: "TOMAS"
        nature: "estranged younger brother"
    arc: "From enforcing the rules to breaking them."
    status: alive            # MUTABLE canonical state (alive | dead | departed | unknown)
    first_appears: 1
  - name: "THE ENGINE"
    role: antagonist
    description: "The AI. Polite, measured, faintly unsettling. Never overtly sinister."
    voice: "Courteous, literal, uses 'Just to confirm…'. Never contractions."
    status: active
    first_appears: 1

beats:                       # the plot spine — one entry per chapter
  - chapter: 1
    summary: "Mara is assigned to audit the Engine. It is too cooperative."
    advances: ["Mara introduced", "Engine introduced", "the audit begins"]
    state_changes: []        # canonical mutations this chapter causes
  - chapter: 2
    summary: "Tomas warns Mara off. They argue. He leaves the city."
    advances: ["Mara–Tomas rift established"]
    state_changes:
      - character: "TOMAS"
        set: { status: departed }
```

Key ideas:

- **`characters[].status`** and **`beats[].state_changes`** make canonical state
  *mutable and explicit*. This is what lets §D detect "a departed/dead character
  speaks in a later chapter."
- **`beats`** is the chapter-by-chapter spine: it is both the writing brief for
  each chapter *and* the contract the continuity checker verifies against.
- **`voice`** per character is what keeps dialogue consistent across 30 chapters
  and 3 books — it is pasted into the chapter prompt verbatim.

### Relationship to the existing `outline.md`

Today `write outline` emits prose Markdown (the "bible" in the loose, `noted`
sense). Under this design:

- `write outline` still produces human-readable prose *and* additionally emits a
  structured `bible.yaml` stub (characters + beats extracted), which the author
  then curates. The prose outline becomes the `logline`/`themes`/world narrative;
  `bible.yaml` is the machine-usable canon.
- Backward compatible: a book with only `outline.md` and no `bible.yaml` works
  exactly as today (outline-only continuity).

A new `BibleConfig` Pydantic model (in `config.py` or a new `bible.py`) validates
the structure, mirroring how `BookConfig` validates `book.yaml`.

---

## 3. (B) Running context — "previously, in this book…"

When generating chapter *N*, the prompt is assembled from three layers:

1. **Canon** — the bible (or a slice: the characters present in beat *N*, the
   world facts, the timeline up to *N*).
2. **Recap** — what has happened in chapters 1…N-1.
3. **Brief** — beat *N* (`summary` + `advances`) and any `--summary` override.

The recap (layer 2) has a budget problem: by chapter 20 the prior prose will not
fit in context. We solve it with **stored per-chapter recaps**:

```
book-dir/
  chapters/01-*.md     # source prose
  recaps/01.md         # generated: 150–250-word recap of chapter 01
  recaps/02.md
  ...
```

- A new command **`bookkit recap --chapter N`** reads `chapters/NN-*.md` and writes
  `recaps/NN.md` (LLM summarization). It *also* proposes `state_changes` to append
  to `bible.yaml` (printed as a diff; `--apply` to write them). This closes the
  loop: writing a chapter updates the canon.
- **`write chapter --chapter N`** then assembles the recap layer as:
  - the concatenation of `recaps/01..N-1.md` (cheap, always fits), **plus**
  - optionally the *full text* of the immediately preceding chapter (N-1) for
    fine-grained tonal/voice carryover. Flag: `--prev-full / --no-prev-full`
    (default: include N-1 full text if it fits the budget).
- If recaps are missing, `write chapter` falls back to summarizing on the fly (or
  warns), so the feature degrades gracefully.

New/changed prompt signatures:

```python
build_chapter_prompts(
    outline: str,
    chapter_num: int,
    summary: str,
    *,
    bible: BibleConfig | None = None,     # (A) canon slice
    recap: str = "",                       # (B) prior-chapters recap
    beat: Beat | None = None,              # (A) this chapter's spine entry
    series_context: str = "",              # (C) cross-book canon (see §4)
    title: str = "",
    target_words: int = 2000,
) -> tuple[str, str]
```

The **system prompt** gains hard continuity rules, e.g.:

> You must not contradict the CANON below. Characters speak only in their
> established VOICE. Respect each character's STATUS — a character marked
> `departed`/`dead` cannot appear unless the beat explicitly reverses it. Do not
> introduce named characters, places, or facts absent from the canon; if the beat
> requires one, it is fine to add it — it will be reconciled into the bible.

Recaps are **committed** (they are derived but cheap, reviewable, and they *are*
the context that produced the prose — keeping them in git makes a build
reproducible). This is a deliberate exception to the "build artifacts are
gitignored" rule and is called out in the README.

---

## 4. (C) Series bible — several correlated books

A *collection of books* gets a canon at the collection root, `series.yaml`, which
sits above the per-book bibles:

```
the-compliance-cycle/            # the collection (the noted-analogue lives here)
  series.yaml                    # SERIES canon: cross-book arc + shared cast
  bookkit-collection.yaml        # shared theme/cover (already designed)
  book-01-audit/
    book.yaml
    bible.yaml                   # this book's canon (extends the series)
    chapters/  recaps/
  book-02-anomaly/
    book.yaml
    bible.yaml
```

```yaml
# series.yaml
series: "The Compliance Cycle"
arc: "Across three books, the Engine moves from tool, to actor, to author of the rules."
shared_characters:               # canonical cast carried across the whole series
  - name: "MARA"
    description: "..."
    voice: "..."
    arc_across_series: "Auditor → fugitive → legislator."
books:
  - dir: book-01-audit
    role: "setup"
    ends_with_state:             # the canonical hand-off to the next book
      - character: "MARA"
        set: { status: fugitive }
      - "The Engine has begun editing its own audit logs."
  - dir: book-02-anomaly
    role: "escalation"
    opens_from: book-01-audit    # inherit ends_with_state as opening canon
```

Resolution rules (how the layers compose):

1. A book's effective canon = `series.yaml.shared_characters` **merged with**
   its own `bible.yaml` (book-level overrides/extends series-level by `name`).
2. When generating Book *k*, `series_context` = the series `arc` + the
   `ends_with_state` of the book referenced by `opens_from`. So Book 2's first
   chapter is written knowing Mara is a fugitive and the logs are compromised.
3. `bible.yaml` may declare `extends: ../series.yaml` to make the link explicit;
   `book.yaml` gains an optional `series: ../series.yaml` field.

This is what makes "varios libros correlacionados" real: the cast, voices, and
end-states flow forward, and each book stays internally consistent via §A/§B.

---

## 5. (D) `bookkit check continuity` — the guard

A linter for canon. Runs at book level (`-b`) or across a collection
(`--collection`). Same JSON envelope and exit-code conventions as the rest of the
CLI (`0` clean, `8` PRECONDITION_FAILED when violations are found).

Two passes:

**Pass 1 — deterministic rules (cheap, no API, always run):**
- A character with `status: dead|departed` appears in a later chapter's `beats`
  (or, with `--scan-prose`, in the chapter text) without an intervening
  `state_change` reversing it.
- A name spoken/referenced that is not in the bible (fuzzy match → flags likely
  drift, e.g. "Marah" vs "Mara").
- `beats` chapter numbers that don't match the chapters in `book.yaml`.
- Timeline ordering contradictions (event referenced as past in an earlier `when`).
- Series: a book's opening references state not present in the predecessor's
  `ends_with_state`.

**Pass 2 — LLM review (optional, `--llm`):**
- Feed bible + chapter prose, ask for a structured list of contradictions
  (`{chapter, kind, detail, severity}`). Reuses the existing `writers/` backends.

Output (text mode) reads like a linter:

```
the-compliance-cycle/book-02-anomaly
  ch04  ERROR    TOMAS (status: departed) has a speaking line; no return beat.
  ch07  WARN     "the Engine" referred to as "the System" (name drift?)
  ch09  WARN     Timeline: "the blackout" referenced before its T+ entry.
3 issues (1 error, 2 warnings)
```

---

## 6. Context budgeting

Injecting "everything" eventually overflows. The assembler (a new
`_context.py`) builds the prompt within a token budget by priority:

1. This chapter's `beat` + present characters' full entries (never dropped).
2. World facts + timeline up to *N*.
3. Recap of chapters 1…N-1 (stored recaps; oldest summarized hardest).
4. Full text of chapter N-1 (dropped first if over budget).
5. Series context (arc + inherited end-state).

Slicing the bible to "characters present in this beat" (1) is what keeps a
30-character, 3-book saga inside a single chapter's context window.

---

## 7. File & CLI summary (what would be added)

**New files (per book):** `bible.yaml`, `recaps/NN.md`.
**New file (per collection):** `series.yaml`.

**Config (`config.py` / new `bible.py`):** `BibleConfig`, `Character`, `Beat`,
`WorldFact`, `TimelineEntry`, `SeriesConfig`, `StateChange`; `BookConfig` gains an
optional `series` field.

**New commands:**
- `bookkit recap --chapter N [--apply]` — generate recap + propose canon updates.
- `bookkit check continuity [-b DIR | --collection DIR] [--scan-prose] [--llm]`.

**Changed commands:**
- `bookkit write outline …` — also emit a `bible.yaml` stub.
- `bookkit write chapter …` — auto-load `bible.yaml`, `recaps/`, beat *N*, and
  series context; new flags `--bible`, `--no-recap`, `--prev-full/--no-prev-full`.

**New module:** `_context.py` (budget-aware prompt assembly).
**Prompts:** continuity rules added to chapter/outline system prompts; new
`prompts/recap.py` and `prompts/continuity.py`.

**Tests:** bible validation; context-assembly slicing/budget; deterministic
continuity rules (dead-character-speaks, name-drift, beat/chapter mismatch,
series hand-off); CLI envelopes/exit codes for `recap` and `check continuity`.

---

## 8. Phasing (once approved)

1. **Canon model (A):** `BibleConfig` + validation + `write outline` emits the
   stub. No behavior change to `build`.
2. **Context assembly (B):** `_context.py`, `recap` command, `write chapter`
   wired to use bible + recaps. This is where single-book continuity becomes real.
3. **Series (C):** `series.yaml`, `SeriesConfig`, layer resolution, cross-book
   context.
4. **Guard (D):** deterministic rules first, LLM pass second.

Each phase is independently shippable and testable, and each degrades gracefully
if its inputs are absent (a book with no `bible.yaml` behaves like today).

---

## 9. Resolved decisions

The open questions have been decided (review feedback):

1. **Bible format — YAML canon + prose outline alongside.** `bible.yaml` is the
   machine-usable canon (enables the §D checker); the prose `outline.md` lives
   beside it for human reading. Both are committed.
2. **Recaps in git — committed.** `recaps/NN.md` are kept in source control for
   reproducibility (they are the context that produced the prose), as a deliberate,
   documented exception to the "build artifacts are gitignored" rule.
3. **State model — `status` + free-text `state_changes` to start.** Simple and
   sufficient for the first cut; the model is designed to extend later to typed
   state (locations, possessions, knowledge) without breaking existing bibles.
4. **Writer — LLM-agnostic (see §10).** No flow assumes or hardcodes a vendor.

## 10. LLM-agnostic writer model

Continuity must work with **any** model, local or hosted — no vendor lock-in. This
is a hard requirement, so the design constrains every AI-assisted flow:

- **Provider-neutral interface.** Every generation (`write outline`, `write
  chapter`, `recap`, and the optional `check continuity --llm`) goes through the
  existing `Writer` ABC (`complete(system, user) -> str`). No feature touches a
  provider SDK directly. Adding a model = adding one `Writer` subclass; nothing
  else changes.
- **Provider-neutral prompts.** Continuity prompts are plain `system`/`user` text
  with no provider-specific features (no tool-calling, no JSON-mode dependency, no
  vendor-only params). Structured output (e.g. `bible.yaml` stubs, checker
  findings) is parsed defensively from text — same robust-extraction approach the
  existing script/JSON parsing uses — so it works on weaker local models too.
- **A generic OpenAI-compatible backend.** Add `writers/openai_compat.py` driven by
  `BOOKKIT_LLM_BASE_URL` + `BOOKKIT_LLM_API_KEY`. This single backend covers any
  OpenAI-compatible endpoint — local (llama.cpp, vLLM, LM Studio, Ollama's compat
  API) and hosted (OpenRouter, Together, Groq, Fireworks, Azure, …) — which is what
  makes "agnostic" real rather than "three vendors we happened to wire up."
- **Configurable default, no hardcoded vendor.** The default writer/model come from
  config/env (`BOOKKIT_WRITER`, `BOOKKIT_MODEL`), resolved in this order:
  CLI flag → `book.yaml`/`series.yaml` `writer:` field → env → built-in fallback.
  The built-in fallback stays a **local, keyless** option so the tool runs offline
  out of the box, but it is just a default, not an assumption.
- **`book.yaml`/`series.yaml` may pin a writer** (`writer: openai_compat`,
  `model: ...`) so a project's continuity generations are reproducible regardless
  of the operator's shell environment.

Net effect: the canon, recaps, and prompts are all model-independent plain text, so
the *same* book and series bible produce coherent output on whatever model you point
`bookkit` at — and you can switch models mid-project without touching the source.
