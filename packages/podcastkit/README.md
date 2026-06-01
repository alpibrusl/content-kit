# podcastkit

**Podcast as Code** — scripts are source, audio is output. Version your show, not your MP3s.

```
podcastkit generate   # synthesize voice lines via TTS → voices/*.mp3
podcastkit assemble   # mix voices + music + SFX via ffmpeg → episode.mp3
```

Supports four TTS backends (mix freely per character), a YAML-driven episode config, and a machine-readable JSON output mode for agent pipelines.

> **Status:** Not on PyPI. Install directly from source (see below). This is a working tool extracted from a real production, not a maintained package — use it, fork it, adapt it.

---

## The concept

A podcast produced with podcastkit is defined entirely in plain text files: a `script.json` with the lines, an `episode.yaml` with the voice cast and mix. The audio is derived from those files the same way a binary is derived from source code — you don't commit it, you build it.

This means a show can be reproduced exactly, re-rendered in a different voice, translated line by line, forked at any point in the story, or audited word by word. The canonical form of the work is the script. The MP3 is a build artifact.

The same pattern applies to any synthesized media. Audio is the current focus because the open-source tooling is mature — local TTS models like Kokoro produce usable results today with no API and no cost. Video and image synthesis are getting there. When they do, the model is the same: source files in, rendered media out, everything version-controlled, everything reproducible.

---

## Install

Requires **Python 3.10+** and **ffmpeg** on `PATH`:

```bash
brew install ffmpeg        # macOS
apt install ffmpeg         # Debian/Ubuntu
winget install ffmpeg      # Windows
```

Clone and install in editable mode:

```bash
git clone https://github.com/alpibrusl/podcastkit.git
cd podcastkit
pip install -e '.[kokoro]'           # Kokoro (local, free, recommended)
```

Install only what you need:

```bash
pip install -e '.[kokoro]'           # Kokoro TTS
pip install -e '.[chatterbox]'       # Chatterbox (local, voice cloning)
pip install -e '.[openai]'           # OpenAI TTS
pip install -e '.[elevenlabs]'       # ElevenLabs
pip install -e '.[kokoro,openai]'    # combine freely
```

Or install directly without cloning (no editable mode):

```bash
pip install 'git+https://github.com/alpibrusl/podcastkit.git[kokoro]'
```

---

## Quick start

```bash
podcastkit new my-show --episodes 3
cd my-show/episode_01
```

Edit `script.json` with your lines and `episode.yaml` with your voice cast, then:

```bash
# Kokoro and Chatterbox run locally — no API key needed.
# For ElevenLabs or OpenAI, set the relevant key:
#   export ELEVENLABS_API_KEY=sk_...
#   export OPENAI_API_KEY=sk-...

podcastkit generate                # writes voices/*.mp3
podcastkit assemble                # writes episode_01.mp3
```

---

## episode.yaml reference

```yaml
title: "Episode 1"
output: "episode_01.mp3"

# backend choices: chatterbox | elevenlabs | kokoro | openai
voices:
  NARRATOR:
    backend: kokoro
    voice_id: bm_george          # Kokoro voice name
  HOST:
    backend: chatterbox
    voice_id: ""                 # path to reference audio for voice cloning, or "" for default
    model_id: standard           # standard | turbo | multilingual
    settings: {exaggeration: 0.5, cfg_weight: 0.5, temperature: 0.8}
  GUEST:
    backend: openai
    voice_id: nova               # alloy | echo | fable | onyx | nova | shimmer
    model_id: tts-1-hd
  SPECIAL:
    backend: elevenlabs
    voice_id: nPczCjzI2devNBz1zQrb
    model_id: eleven_multilingual_v2
    settings: {stability: 0.70, similarity_boost: 0.70, style: 0.0, use_speaker_boost: true}

# Ordered voice lines; pre_silence is seconds of silence prepended to each line
timeline:
  - {id: narr_01, pre_silence: 0.5}
  - {id: host_01, pre_silence: 0.4}

# Long background tracks (looped)
bg_tracks:
  - file: sfx/office_ambience.mp3
    start: [narr_01, start, 0.0]     # [line_id, "start"|"end", offset_seconds]
    fade_in: 2.0
    fade_out_at: [host_01, end, 0.0]
    fade_out_dur: 2.0
    volume_db: -25.0
    loop: true

# Short one-shot SFX
sfx_hits:
  - file: sfx/notification.mp3
    at: [narr_01, end, 0.1]
    volume: 0.6
```

`script.json` is a flat list of `{id, character, text}` entries. The `id` must match `timeline` entries; `character` must match `voices` keys.

---

## TTS backends

| Backend | Key needed | Quality | Notes |
|---------|-----------|---------|-------|
| `kokoro` | None | Good | Local ~300 MB model; Apache 2.0 |
| `chatterbox` | None | Good | Local ~500 MB model; voice cloning; Apache 2.0 |
| `openai` | `OPENAI_API_KEY` | Very good | `tts-1` or `tts-1-hd`; commercial API |
| `elevenlabs` | `ELEVENLABS_API_KEY` | Highest | Free tier ~10k chars/month; commercial API |

Backends are per-character — mix freely. Kokoro and Chatterbox run offline with no ongoing cost.

Reruns of `generate` are cheap: any voice file ≥ 5 KB on disk is skipped. Delete a file and rerun to regenerate a single line.

---

## Commands

### `podcastkit new <name>`

Scaffold a new project directory.

```
Options:
  --episodes  -n  INTEGER   Number of episode stubs to create  [default: 1]
  --dest      -d  PATH      Parent directory                   [default: .]
  --output    -o  text|json
```

### `podcastkit generate`

Synthesize voice lines from `script.json` using the backends in `episode.yaml`.

```
Options:
  --episode-dir  -e  PATH              Episode directory  [default: .]
  --backend          chatterbox|elevenlabs|kokoro|openai   Override all characters
  --force                              Regenerate existing files
  --dry-run                            Show what would be generated (no API calls)
  --output       -o  text|json
```

### `podcastkit assemble`

Two-pass ffmpeg pipeline: concatenate voice lines → mix bg tracks + SFX → encode MP3.

```
Options:
  --episode-dir  -e  PATH   Episode directory  [default: .]
  --dry-run                 Validate config and voice files without running ffmpeg
  --output       -o  text|json
```

---

## Agent-friendly output

Every command accepts `--output json` and returns a structured envelope:

```json
{
  "ok": true,
  "command": "assemble",
  "data": {
    "output": "episode_01.mp3",
    "duration_s": 487.3,
    "size_mb": 11.2,
    "integrated_lufs": -16.1,
    "true_peak_dbtp": -1.4
  },
  "meta": {"duration_ms": 62000, "version": "0.1.0"}
}
```

Error responses include a machine-readable `code` and a human-readable `hint`:

```json
{
  "ok": false,
  "command": "generate",
  "error": {
    "code": "NOT_FOUND",
    "message": "episode.yaml not found in /tmp",
    "hint": "Run 'podcastkit new <name>' to scaffold a project first."
  },
  "meta": {"duration_ms": 0, "version": "0.1.0"}
}
```

Semantic exit codes: `0` success · `2` invalid args · `3` not found · `7` upstream error · `8` precondition failed · `9` dry run.

`generate` and `assemble` stream NDJSON progress lines before the final envelope when `--output json` is set, so agents can parse intermediate status line-by-line.

Run `podcastkit introspect` for the full command tree as JSON (used by agent frameworks for capability discovery).

---

## Loudness

`assemble` reports integrated loudness after encoding. Podcast standard is roughly **-16 LUFS**. If you're off, run a loudnorm pass:

```bash
ffmpeg -i episode_01.mp3 \
  -af loudnorm=I=-16:TP=-1.5:LRA=11 \
  -c:a libmp3lame -b:a 192k \
  episode_01_norm.mp3
```

---

## Example project

**[NOTED](https://github.com/alpibrusl/noted)** — AGREEABLE and its 24-episode Season 2 anthology — is the project this pipeline was extracted from. All 24 episodes were produced with this tool using Kokoro as the TTS backend. Scripts, voice assignments, and production scripts are at [github.com/alpibrusl/noted](https://github.com/alpibrusl/noted).

---

## Technology disclosure

This project is built on top of the following tools and models. Using it means using them — their licenses, limitations, and terms apply.

**Audio synthesis**
- [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) — open-source TTS model, Apache 2.0. Runs locally. Outputs are yours to use freely.
- [Chatterbox](https://github.com/resemble-ai/chatterbox) — open-source TTS with voice cloning, Apache 2.0. Runs locally.
- [OpenAI TTS](https://platform.openai.com/docs/guides/text-to-speech) — commercial API. Outputs governed by OpenAI's terms of service.
- [ElevenLabs](https://elevenlabs.io) — commercial API. Outputs governed by ElevenLabs' terms of service.

**Audio assembly**
- [ffmpeg](https://ffmpeg.org) — LGPL 2.1+ / GPL 2+. The heavy lifting for all audio mixing and encoding.

**Script writing (optional, `podcastkit write`)**
- [Claude](https://anthropic.com) (Anthropic), [GPT-4](https://openai.com) (OpenAI), [Ollama](https://ollama.com) (local) — LLM backends for generating series bibles and episode scripts. Commercial APIs where applicable; Ollama runs locally. Outputs are AI-generated text; review and edit before production.

**What this means in practice:** if you use only Kokoro or Chatterbox with Ollama for writing, the entire pipeline runs locally with no external services and no API costs. All components in that path are open-source.

---

## Layout

```
my-show/
├── episode_01/
│   ├── episode.yaml        # voice cast + timeline + bg/sfx config
│   ├── script.json         # [{id, character, text}, ...]
│   ├── voices/             # generated per-line MP3s (gitignore this)
│   ├── sfx/                # your SFX files
│   ├── music/              # your music files
│   ├── build/              # intermediate WAV track (gitignore this)
│   └── episode_01.mp3      # final output (gitignore this)
└── episode_02/
    └── ...
```

---

## License

[EUPL-1.2](https://eupl.eu/1.2/en/) — European Union Public Licence, a copyleft license compatible with GPL, AGPL, and MPL.
