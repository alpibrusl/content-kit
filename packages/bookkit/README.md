# bookkit

**Book as Code** — Markdown chapters are source, the EPUB/PDF is output. Version your manuscript, not your exports.

```
bookkit new "My Book" -n 12   # scaffold book.yaml + chapters/01..12
bookkit build -f epub         # render Markdown chapters → build/my-book.epub
bookkit build -f pdf          # …or a print-ready PDF
```

A sibling of [podcastkit](https://github.com/alpibrusl/podcastkit): same philosophy, same CLI conventions (Typer, YAML config, JSON output mode, semantic exit codes), but the build artifact is a book instead of an audio file.

> **Status:** early. The HTML renderer is built in and dependency-free; EPUB and PDF are optional extras. Not on PyPI — install from source.

---

## The concept

A book produced with bookkit is defined entirely in plain text: a `book.yaml` with the metadata, theme, and chapter order, plus one Markdown file per chapter. The `.epub` and `.pdf` are derived from those files the same way a binary is derived from source code — you don't commit them, you build them.

This means a book can be reproduced exactly, re-rendered in a different theme, re-paginated for a different page size, translated chapter by chapter, or audited word by word. The canonical form of the work is the Markdown. The EPUB is a build artifact.

It is the same pattern podcastkit applies to audio: source files in, rendered media out, everything version-controlled, everything reproducible.

---

## Install

Requires **Python 3.10+**.

```bash
git clone https://github.com/alpibrusl/bookkit.git
cd bookkit
pip install -e .              # core: HTML rendering, scaffolding, build pipeline
pip install -e '.[epub]'      # EPUB rendering (ebooklib)
pip install -e '.[pdf]'       # PDF rendering (WeasyPrint)
pip install -e '.[epub,pdf]'  # both
pip install -e '.[claude]'    # AI writing with Claude   (or [openai]; Ollama needs no extra)
```

WeasyPrint needs system libraries (Pango, cairo) for PDF output — see its install docs for your platform.

---

## Workflow

```bash
# 1. Scaffold a book
bookkit new "The Compliance Engine" -n 8

# 2. (optional) Draft from a concept with an LLM — also writes a bible.yaml (canon)
bookkit write outline "A field guide to corporate AI governance" -n 8

# 3. Write chapters. Each chapter is generated WITH continuity context:
#    the bible + this chapter's beat + a recap of earlier chapters.
bookkit write chapter --outline outline.md --chapter 1
bookkit recap --chapter 1 --apply        # summarize ch.1 → recaps/01.md, update canon
bookkit write chapter --outline outline.md --chapter 2   # ch.2 "knows" what happened in ch.1
bookkit recap --chapter 2 --apply
# …repeat. Or hand-write chapters in chapters/NN-*.md (plain Markdown).

# 4. Build
bookkit build -f epub
bookkit build -f pdf
```

Every command supports `--output json` for agent pipelines and returns semantic exit codes
(`0` success, `2` bad args, `3` not found, `8` precondition failed, `9` dry-run).

---

## Continuity (the bible)

For plot/character coherence across chapters — and across correlated books in a series —
`bookkit` keeps a **`bible.yaml`**: a structured, committed canon of characters (with their
voice and mutable status), the world, the timeline, and per-chapter plot beats. `bookkit new`
scaffolds a starter `bible.yaml`, and `bookkit write outline` emits a filled one alongside the
prose outline. The canon is plain, auditable data — continuity lives in source control, not in
a model's memory.

How coherence is actually enforced:

- **`write chapter`** feeds the model three context layers before it writes: the **canon**
  (the bible, sliced to characters introduced by this chapter), this chapter's **beat**, and a
  **recap** of earlier chapters (plus the previous chapter's full text for voice carryover).
  The system prompt forbids contradicting the canon or violating a character's `status`.
- **`recap --chapter N [--apply]`** summarizes a finished chapter into `recaps/NN.md` and
  proposes canonical state changes (e.g. a character departs); `--apply` writes them back into
  `bible.yaml`, so the *next* chapter is generated against the updated state.

### Correlated books (series)

`bookkit series new "<Title>" -n 3` scaffolds a **collection**: a `series.yaml` (the cross-book
canon — shared cast, the overall arc, and each book's role and ending state) plus linked book
sub-directories. When a book's `book.yaml` points at the series, `write chapter` folds the
**shared cast** into that book's canon and feeds the **previous book's ending state** into the
prompt — so book 2 is written knowing how book 1 left things:

```yaml
# series.yaml
series: "The Compliance Cycle"
arc: "The Engine moves from tool to author of the rules."
shared_characters:
  - { name: "MARA", role: protagonist, voice: "Clipped." }
books:
  - dir: book-01
    role: setup
    ends_with_state: [{ character: "MARA", set: { status: fugitive } }]
  - dir: book-02
    role: escalation
    opens_from: book-01      # inherits book-01's ending state as opening canon
```

### Checking continuity

`bookkit check continuity` is a linter for the canon. It runs deterministic rules — a
dead/departed character reappearing, name drift, beats that don't match the chapters,
broken series hand-offs — and exits `8` if it finds errors (so it gates CI):

```bash
bookkit check continuity -b .                 # one book, against its bible.yaml
bookkit check continuity -b . --scan-prose    # also scan chapter text, not just beats
bookkit check continuity --collection .       # a whole series (series.yaml + every book)
bookkit check continuity -b . --llm           # add an optional LLM contradiction pass
bookkit check continuity -b . --strict        # treat warnings as failures too
```

Full design and rule list: [`docs/continuity.md`](docs/continuity.md).

## LLM-agnostic

Every AI-assisted command (`write outline`, `write chapter`) is provider-neutral. Pick a
backend with `-w` (`claude` | `openai` | `ollama` | `openai_compat`) or set a default with
`$BOOKKIT_WRITER` / `$BOOKKIT_MODEL`. The `openai_compat` backend talks to **any**
OpenAI-compatible endpoint — local (llama.cpp, vLLM, LM Studio) or hosted (OpenRouter,
Together, Groq, …) — via `$BOOKKIT_LLM_BASE_URL` + `$BOOKKIT_LLM_API_KEY`, with no SDK or
extra required. The default stays local and keyless so it runs offline out of the box.

---

## `book.yaml` reference

```yaml
title: "The Compliance Engine"
subtitle: "A Field Guide"
author:
  name: "A. Author"
  bio: "Writes about systems."
language: en                        # also localizes generated labels (Contents, ...)
output: "compliance-engine.epub"   # build/<stem>.<format>
cover: "cover.png"                  # embedded in EPUB; a cover page in HTML/PDF
isbn: ""
theme:
  base_font: serif                  # serif | sans | mono
  page_size: 6x9                    # 6x9 | 5x8 | a4 | letter  (PDF geometry)
  font_size_pt: 11.0
  stylesheet: ""                    # path to custom CSS, or "" for the built-in
  stylesheet_mode: replace          # replace (own every rule) | extend (override on top)
chapters:                           # ordered; the first "# Heading" is the title
  - { file: chapters/01-intro.md, title: "" }
  - { file: chapters/02-setup.md, title: "Getting Started" }
front_matter: [title_page, toc]     # also: copyright
back_matter:                        # keywords and/or Markdown files, in order
  - { file: COLOPHON.md, title: "" }
  - about_author
```

Generated headings ("Contents", "About the Author", "Copyright", …) follow
`language:` — `es`, `fr`, `de`, `it`, `pt` and `ca` ship out of the box, and
anything else falls back to English.

---

## Renderers

| format | extra | engine | notes |
|--------|-------|--------|-------|
| `html` | *(built in)* | `markdown` | single self-contained file; always available |
| `epub` | `[epub]` | `ebooklib` | per-chapter XHTML + navigation, reflowable |
| `pdf`  | `[pdf]`  | `weasyprint` | paged, print-ready; page size from theme |

All three share one stylesheet and one HTML model, so a book looks consistent across formats.

---

## Audiobook (bridge to podcastkit)

The same source that renders to EPUB and PDF can render to **audio**, by handing
off to [podcastkit](https://github.com/alpibrusl/podcastkit) — the sibling tool
that turns a script into an MP3 via TTS + ffmpeg. `bookkit audiobook` reads a
book's Markdown chapters and emits a ready-to-render podcastkit project: one
episode per chapter, each with a `script.json` (the narration, chunked into
TTS-sized lines on sentence boundaries) and an `episode.yaml` (the voice cast +
timeline).

```bash
bookkit audiobook -b .                       # → ./<slug>-audiobook/chapter_NN/
bookkit audiobook -b . --dry-run             # show episodes, lines, char counts
bookkit audiobook -b . --backend openai --voice nova   # cast the narrator
bookkit audiobook -b . --cast                # full-cast: attribute dialogue to characters
```

The two tools stay **decoupled** — bookkit never imports podcastkit; it just
writes files podcastkit knows how to read. Render them with podcastkit:

```bash
cd <slug>-audiobook/chapter_01
podcastkit generate      # script.json → voices/*.mp3 (TTS)
podcastkit assemble      # → chapter_01.mp3
```

**The bible is the voice cast.** When a `bible.yaml` is present, every character
in the canon becomes an entry in the episode's `voices` map, with its canonical
`voice` description carried across as a casting note. v1 narrates everything as a
single `NARRATOR` voice (a classic single-reader audiobook); the rest of the cast
is wired in with placeholder voice ids, so turning a novel into a *full-cast*
reading is a matter of assigning voices — not re-deriving who the characters are.
The character a reader meets, an EPUB renders, and a narrator voices is one
definition, in one place.

**Full-cast readings.** `--cast` attributes quoted (`"..."`) and dash-led
(`—...`, Spanish/French) dialogue to the bible character an attribution cue names
(`said X` / `—dijo X`), giving each their own voice. Attribution is deliberately
conservative — when no cue clearly names a speaker, the line stays with the
narrator, because a wrong voice is more jarring than a narrated one. (First-person
narration therefore stays mostly narrated, which is correct.)

> **Note on cost & language.** Local backends (`kokoro`, `chatterbox`) are free
> and English-centric; `openai` and `elevenlabs` are paid per character and
> handle other languages (e.g. Spanish) better. `audiobook` reports the total
> character count so you can estimate paid-TTS spend before rendering.

---

## Storyboard (the visual tier)

The same canon also drives **visuals**. `bookkit storyboard` turns a book into a
panel/shot script — one `storyboard.json` per chapter — that a comic or video
tool renders:

```bash
bookkit storyboard -b .            # → ./<slug>-storyboard/chapter_NN/storyboard.json
bookkit storyboard -b . --dry-run  # show chapters and panel counts
```

Each panel carries a **scene** description, the **dialogue** spoken in it
(attributed with the same engine as `--cast`), the **characters present**, and
**art notes** pulled from `bible.yaml` — so a character looks the same in every
panel they appear in, the same way the bible keeps them consistent in prose and
audio. bookkit produces the script; rendering pixels is a separate tier, exactly
as rendering audio is podcastkit's job — one canonical source, many media.

## Orchestrating the pipeline

The tiers compose. `scripts/render-media.sh <book-dir> [--cast]` runs the whole
chain (audiobook → podcastkit render, plus the storyboard), and the
`skills/book-to-media` agent skill lets Claude drive it from a plain request
("make a full-cast audiobook of book-03"). See [docs/PRODUCT.md](docs/PRODUCT.md)
for why the product surface is a skill/MCP rather than a web app — for now.

---

## Collections

A *collection of books* is a parent directory of book folders, scaffolded with
`bookkit series new` and bound together by a `series.yaml` (see [Correlated books](#correlated-books-series)
above). Build each book with `bookkit build -b <book-dir>`.

---

## License

EUPL-1.2 — see [LICENSE](LICENSE).
