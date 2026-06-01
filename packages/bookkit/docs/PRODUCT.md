# Product direction: web/app vs. MCP/skill?

**Short answer: start as a skill (+ optional MCP), not a web app.** Build the
web app only once a repeatable workflow exists that a UI would make faster — and
even then, wrap the CLIs, don't replace them.

## Why

The value of this platform is **one canonical source rendering to many media**
(book → EPUB/PDF, audiobook, storyboard → comic/video). That value lives in:

1. the **canon** (`book.yaml` + `bible.yaml` + chapters), and
2. the **CLIs** that transform it (`bookkit`, `podcastkit`).

A web app adds none of that — it's a *front end* to it. Building UI first means
building auth, hosting, job queues, file storage, and a render farm before
you've proven anyone wants chapter-12-as-a-full-cast-audiobook. That's months of
infra around a thesis you can validate this week.

An **agent skill** is the opposite trade. The CLIs are already the product; the
skill is just the instruction sheet that lets Claude drive them
(`skills/book-to-media/SKILL.md`). Near-zero infra, runs anywhere the user
already is (terminal, IDE, Claude Code on the web), and it *is* the orchestrator
— the glue layer that chains two decoupled tools. We shipped it alongside a
plain `scripts/render-media.sh` for the no-agent case.

## The progression

| Stage | Form | What it buys | Cost |
|------|------|--------------|------|
| **0 — now** | CLIs + `scripts/render-media.sh` | Reproducible, scriptable, CI-able pipeline | shipped |
| **1 — now** | **Agent skill** (`book-to-media`) | Natural-language orchestration; "make an audiobook of book-03" | shipped |
| **2 — next** | **MCP server** | Exposes `audiobook`/`storyboard`/`build` as typed tools to *any* MCP client (Claude Desktop, etc.); structured results, not parsed text | small — wrap the existing `introspect` contract |
| **3 — later** | **Web app** | Non-technical authors; preview/scrub audio; click-to-cast voices; hosted renders | large — only worth it with real demand |

Stage 2 is cheap because the CLIs already emit JSON envelopes and ship a hidden
`introspect` command that dumps the full command tree — an MCP server is a thin
adapter over that, not new logic.

## When a web app *does* become right

Build it when **all three** are true:
- non-technical authors are the target user (writers, not engineers);
- the loop is "tweak cast → re-render → listen", which a CLI makes tedious and a
  UI makes pleasant (waveform scrubbing, click-to-assign voices);
- hosted rendering (paid TTS/image/video at scale) is a service people will pay
  for.

Until then, every hour goes into the **renderers and the canon** — a comic/video
backend for `storyboard.json`, better dialogue attribution, more voices — not
into UI chrome. The skill and MCP keep the surface area honest: if a capability
isn't useful as a tool an agent can call, a button won't save it.
