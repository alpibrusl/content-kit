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

# 2. (optional) Draft from a concept with an LLM
bookkit write outline "A field guide to corporate AI governance" -n 8 -w claude
bookkit write chapter --outline outline.md --chapter 1 -w claude

# 3. Write your chapters in chapters/NN-*.md (plain Markdown)

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
a model's memory. Full design (running recaps, series bibles, and a `check continuity` guard):
[`docs/continuity.md`](docs/continuity.md).

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
language: en
output: "compliance-engine.epub"   # build/<stem>.<format>
cover: "cover.png"                  # optional, used by the EPUB renderer
isbn: ""
theme:
  base_font: serif                  # serif | sans | mono
  page_size: 6x9                    # 6x9 | 5x8 | a4 | letter  (PDF geometry)
  font_size_pt: 11.0
  stylesheet: ""                    # path to custom CSS, or "" for the built-in
chapters:                           # ordered; the first "# Heading" is the title
  - { file: chapters/01-intro.md, title: "" }
  - { file: chapters/02-setup.md, title: "Getting Started" }
front_matter: [title_page, toc]     # also: copyright
back_matter:  [about_author]
```

---

## Renderers

| format | extra | engine | notes |
|--------|-------|--------|-------|
| `html` | *(built in)* | `markdown` | single self-contained file; always available |
| `epub` | `[epub]` | `ebooklib` | per-chapter XHTML + navigation, reflowable |
| `pdf`  | `[pdf]`  | `weasyprint` | paged, print-ready; page size from theme |

All three share one stylesheet and one HTML model, so a book looks consistent across formats.

---

## Collections

A *collection of books* is a parent directory of book folders that share a theme and
cover style — the same way a podcast network groups shows. Group them under one repo
(see the companion content repo, the book-world analogue of `noted`) and build each
with `bookkit build -b <book-dir>`.

---

## License

EUPL-1.2 — see [LICENSE](LICENSE).
