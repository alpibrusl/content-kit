# content-kit

A monorepo for the content platform: **one canonical source, many rendered
media.** A shared core defines the cross-tool contracts and plumbing; each media
tier is a thin package that produces or renders against those contracts.

```
packages/
  core/         content-kit-core — the shared spine (imported by everything)
  bookkit/      books as code → EPUB / PDF, and the audio/visual bridges
  podcastkit/   scripts → audio dramas & podcasts (TTS + ffmpeg mixing)
  mcp/          content-kit-mcp — an MCP server exposing the CLIs as agent tools
```

## Architecture

The dependency arrow points one way and is enforced in CI (import-linter):

- **`content-kit-core`** owns what every tool shares — the CLI output/exit-code
  protocol, the LLM-agnostic `Writer` factory, the story **bible/canon** model,
  and the **bridge contracts**: the schemas for the artifacts one tool produces
  and another consumes (`episode.yaml` + `script.json` for audio,
  `storyboard.json` for visual). Core never imports a renderer.
- **The renderers never import each other.** The link between tools is a written
  *data artifact* validated against a shared model — never a function call — so
  they stay decoupled siblings. `bookkit audiobook` emits a podcastkit project
  and validates it against the very `EpisodeConfig` that `podcastkit assemble`
  loads, so the contract cannot silently drift: a mismatch fails in bookkit's
  own tests, not at the consumer.

Heavy, tier-specific dependencies stay in their own package's extras — an EPUB
author never installs a TTS/torch stack, and vice versa.

## Development

The workspace uses [uv](https://docs.astral.sh/uv/). Each package is
independently installable; for local work, install the three editable:

```bash
pip install -e ./packages/core \
            -e './packages/bookkit[epub,dev]' \
            -e './packages/podcastkit[dev]'

ruff check packages && ruff format --check packages
lint-imports                       # the dependency-arrow contracts
pytest                             # every package, one run
```

### Driving the toolchain from an agent

`content-kit-mcp` exposes every CLI command as an MCP tool, generated from each
CLI's own `introspect` contract (so it never drifts):

```bash
pip install -e ./packages/mcp     # pulls in bookkit + podcastkit
content-kit-mcp                   # serve over stdio
```

See each package's own `README.md` for tier-specific usage.

## License

Licensed under the **[European Union Public Licence v1.2](LICENSE)** (EUPL-1.2) —
an OSI-approved licence: use, study, modify and redistribute freely, including
commercially, provided derivative works that you distribute are shared under the
EUPL (or a compatible licence). See [`LICENSE`](LICENSE) for the full text.
