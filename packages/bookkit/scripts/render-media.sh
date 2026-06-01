#!/usr/bin/env bash
#
# render-media.sh — render a book to audio (and a storyboard) by composing the
# two CLIs. This is the *orchestrator*: the deliberately thin glue that runs
# bookkit (which owns the canonical source) and then podcastkit (which owns
# audio rendering). The tools never import each other; this script — or an agent,
# or a CI job — is what chains them.
#
# Usage:
#   scripts/render-media.sh <book-dir> [--cast] [--backend NAME] [--voice ID]
#
# Requires `bookkit` and `podcastkit` on PATH (pip install both).
set -euo pipefail

BOOK_DIR="${1:?usage: render-media.sh <book-dir> [--cast] [--backend NAME] [--voice ID]}"
shift || true

CAST_FLAG=""
BACKEND="kokoro"
VOICE="bm_george"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --cast) CAST_FLAG="--cast"; shift ;;
    --backend) BACKEND="$2"; shift 2 ;;
    --voice) VOICE="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

command -v bookkit >/dev/null || { echo "bookkit not on PATH (pip install bookkit)" >&2; exit 1; }
command -v podcastkit >/dev/null || { echo "podcastkit not on PATH (pip install podcastkit)" >&2; exit 1; }

echo "==> 1/3  bookkit audiobook  (canon -> podcastkit project)"
# Capture the project path bookkit chose from its JSON envelope.
PROJECT="$(bookkit audiobook -b "$BOOK_DIR" --backend "$BACKEND" --voice "$VOICE" $CAST_FLAG \
  --force -o json | python -c 'import json,sys; print(json.load(sys.stdin)["data"]["project"])')"
echo "    project: $PROJECT"

echo "==> 2/3  bookkit storyboard (canon -> visual script)"
bookkit storyboard -b "$BOOK_DIR" --force >/dev/null
echo "    storyboard written"

echo "==> 3/3  podcastkit render  (project -> one MP3 per chapter)"
for ep in "$PROJECT"/chapter_*/; do
  [[ -d "$ep" ]] || continue
  echo "    - $(basename "$ep")"
  podcastkit generate -e "$ep"
  podcastkit assemble -e "$ep"
done

echo "==> done. MP3s under $PROJECT/chapter_*/"
