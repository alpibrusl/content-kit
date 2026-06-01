---
name: book-to-media
description: >-
  Turn a bookkit book into other media — an audiobook (via podcastkit) or a
  storyboard for a comic/video. Use when the user asks to "make an audiobook",
  "narrate this book", "do a full-cast reading", "storyboard a chapter", or
  otherwise render a book project into audio or visuals. Assumes a book
  directory with book.yaml (+ optional bible.yaml).
---

# book-to-media

bookkit and podcastkit are **decoupled sibling CLIs**. bookkit owns the
*canonical source* (Markdown chapters, `book.yaml`, `bible.yaml`); podcastkit
owns *audio rendering*. They never import each other — **you are the
orchestrator** that chains them. One canon, many rendered media.

## The pipeline

```
book.yaml + chapters/ + bible.yaml          (canonical source — bookkit)
        │
        ├─ bookkit audiobook  ──►  podcastkit project (script.json + episode.yaml)
        │                              │
        │                              └─ podcastkit generate && assemble ──► MP3s
        │
        └─ bookkit storyboard ──►  storyboard.json (panels) ──► comic/video renderer
```

## How to make an audiobook

1. **Emit the project** (the bible's cast becomes the voice cast automatically):
   ```bash
   bookkit audiobook -b <book-dir> --backend kokoro --voice bm_george
   # full-cast reading (attribute dialogue to characters):
   bookkit audiobook -b <book-dir> --cast --backend openai
   ```
   Use `--dry-run -o json` first to report episodes, line counts, and total
   characters (the cost estimate for paid TTS).
2. **Render each chapter** with podcastkit:
   ```bash
   for ep in <book-dir>/<slug>-audiobook/chapter_*/; do
     podcastkit generate -e "$ep" && podcastkit assemble -e "$ep"
   done
   ```
   Or just run `scripts/render-media.sh <book-dir> [--cast]`, which does all of
   the above.

## How to make a storyboard (comic / video script)

```bash
bookkit storyboard -b <book-dir>
```
Produces one `storyboard.json` per chapter: ordered panels with a scene
description, attributed dialogue, the characters present, and **art notes pulled
from `bible.yaml`** so a character looks the same in every panel. There is no
built-in pixel renderer yet — hand the panels to an image/video tool.

## Guidance

- **Voices & cost.** `kokoro`/`chatterbox` are local and free (English-centric);
  `openai`/`elevenlabs` are paid per character and handle other languages (e.g.
  Spanish) far better. Always surface the character count before a paid render.
- **Cast placeholders.** With a `bible.yaml`, every character is pre-seeded in
  `episode.yaml` with `voice_id: REPLACE_ME` and a casting note. For a full-cast
  reading, fill those in before rendering.
- **Idempotent & safe.** Both commands preserve hand-edited files unless
  `--force` is passed, so re-running never clobbers a tuned cast or script.
- **Attribution is conservative.** `--cast` only assigns a character voice when
  an attribution cue ("said X", "—dijo X") clearly names one; otherwise the line
  stays with the narrator. First-person narration stays mostly narrated — that's
  correct, not a bug.
