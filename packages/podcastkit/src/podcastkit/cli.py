from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import typer
import yaml

from ._exit_codes import ExitCode
from ._output import (
    OutputFormat,
    emit,
    emit_progress,
    error_envelope,
    success_envelope,
)
from ._script import derive_timeline, derive_voices_stub, extract_json, normalize_script
from .assemble import assemble
from .backends import get_backend
from .config import EpisodeConfig
from .prompts import build_bible_prompts, build_script_prompts
from .scaffold import scaffold_project
from .sfx import generate_music, generate_sfx
from .writers import get_writer

VERSION = "0.1.0"
MIN_VALID_BYTES = 5 * 1024

app = typer.Typer(
    name="podcastkit",
    help="CLI for producing audio dramas and podcasts with TTS + ffmpeg mixing.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_config(episode_dir: Path, cmd: str, fmt: OutputFormat) -> EpisodeConfig:
    yaml_path = episode_dir / "episode.yaml"
    if not yaml_path.exists():
        _die(
            cmd,
            fmt,
            code=ExitCode.NOT_FOUND,
            message=f"episode.yaml not found in {episode_dir}",
            hint="Run 'podcastkit new <name>' to scaffold a project first.",
        )
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return EpisodeConfig.model_validate(raw)


def _load_script(episode_dir: Path, cmd: str, fmt: OutputFormat) -> list[dict]:
    json_path = episode_dir / "script.json"
    if not json_path.exists():
        _die(
            cmd,
            fmt,
            code=ExitCode.NOT_FOUND,
            message=f"script.json not found in {episode_dir}",
            hint='Add a script.json with [{"id": ..., "character": ..., "text": ...}] entries.',
        )
    return json.loads(json_path.read_text(encoding="utf-8"))


def _die(
    cmd: str,
    fmt: OutputFormat,
    *,
    code: ExitCode,
    message: str,
    hint: str | None = None,
    hints: list[str] | None = None,
) -> None:
    envelope = error_envelope(cmd, code=code.name, message=message, hint=hint, hints=hints)
    emit(envelope, fmt)
    raise typer.Exit(code=code)


# ---------------------------------------------------------------------------
# Command: new
# ---------------------------------------------------------------------------


@app.command("new")
def cmd_new(
    name: str = typer.Argument(..., help="Project name (used as directory name)."),
    episodes: int = typer.Option(1, "--episodes", "-n", help="Number of episode stubs to create."),
    dest: Path = typer.Option(
        Path("."), "--dest", "-d", help="Parent directory for the new project."
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", "-o", help="Output format (text|json)."
    ),
) -> None:
    """Create a new podcast project directory with episode stubs."""
    t0 = time.time()
    project_dir = dest.resolve() / name
    scaffold_project(name, project_dir, num_episodes=episodes)

    data = {
        "project": name,
        "path": str(project_dir),
        "episodes": [f"episode_{i:02d}" for i in range(1, episodes + 1)],
    }
    if output == OutputFormat.text:
        print(f"Created project '{name}' at {project_dir}")
        for ep in data["episodes"]:
            print(f"  {ep}/")
            print("    episode.yaml")
            print("    script.json")
    else:
        emit(success_envelope("new", data, start_time=t0), output)


# ---------------------------------------------------------------------------
# Command: generate
# ---------------------------------------------------------------------------


@app.command("generate")
def cmd_generate(
    episode_dir: Path = typer.Option(
        Path("."),
        "--episode-dir",
        "-e",
        help="Episode directory containing episode.yaml and script.json.",
    ),
    backend_override: str | None = typer.Option(
        None,
        "--backend",
        help="Override TTS backend for all characters (chatterbox|elevenlabs|kokoro|openai).",
    ),
    force: bool = typer.Option(
        False, "--force", help="Regenerate files even if they already exist."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be generated without calling any API."
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", "-o", help="Output format (text|json)."
    ),
) -> None:
    """Synthesize voice lines via TTS and save them to voices/."""
    t0 = time.time()
    cmd = "generate"
    episode_dir = episode_dir.resolve()
    config = _load_config(episode_dir, cmd, output)
    script = _load_script(episode_dir, cmd, output)

    voices_dir = episode_dir / "voices"

    # Validate characters
    missing_voices = sorted({e["character"] for e in script if e["character"] not in config.voices})
    if missing_voices:
        _die(
            cmd,
            output,
            code=ExitCode.INVALID_ARGS,
            message=f"Characters in script.json have no voice in episode.yaml: {missing_voices}",
            hint="Add a voices: entry for each character in episode.yaml.",
        )

    # --- Dry run ---
    if dry_run:
        voices_dir.mkdir(parents=True, exist_ok=True)
        planned: list[dict] = []
        for entry in script:
            dest_path = voices_dir / f"{entry['id']}.mp3"
            voice_cfg = config.voices[entry["character"]]
            backend = backend_override or voice_cfg.backend
            if not force and dest_path.exists() and dest_path.stat().st_size >= MIN_VALID_BYTES:
                planned.append(
                    {
                        "id": entry["id"],
                        "character": entry["character"],
                        "action": "skip",
                        "reason": f"exists ({dest_path.stat().st_size // 1024} KB)",
                    }
                )
            else:
                planned.append(
                    {
                        "id": entry["id"],
                        "character": entry["character"],
                        "action": "generate",
                        "backend": backend,
                    }
                )
        if output == OutputFormat.text:
            print(f"Dry run — {len(planned)} lines:")
            for p in planned:
                if p["action"] == "skip":
                    print(f"  SKIP  {p['id']:<12s}  {p['character']}  ({p['reason']})")
                else:
                    print(f"  GEN   {p['id']:<12s}  {p['character']}  via {p['backend']}")
        else:
            emit(
                success_envelope(cmd, {}, dry_run=True, planned_actions=planned, start_time=t0),
                output,
            )
        raise typer.Exit(ExitCode.DRY_RUN)

    # --- Synthesize ---
    voices_dir.mkdir(parents=True, exist_ok=True)
    total = len(script)
    skipped = generated = errors = 0

    for i, entry in enumerate(script, 1):
        line_id: str = entry["id"]
        character: str = entry["character"]
        text: str = entry["text"]
        dest_path = voices_dir / f"{line_id}.mp3"

        if not force and dest_path.exists() and dest_path.stat().st_size >= MIN_VALID_BYTES:
            skipped += 1
            if output == OutputFormat.text:
                size_kb = dest_path.stat().st_size // 1024
                print(f"[{i:02d}/{total}] {line_id:<12s}  skip (exists, {size_kb} KB)")
            else:
                emit_progress(line_id, "skipped", detail=f"{character} {i}/{total}")
            continue

        if output == OutputFormat.text:
            print(f"[{i:02d}/{total}] {line_id:<12s}  {character:<10s}  {text[:60]!r}")
        else:
            emit_progress(line_id, "generating", detail=f"{character} {i}/{total}")

        voice_cfg = config.voices[character]
        effective_backend = backend_override or voice_cfg.backend
        if backend_override and backend_override != voice_cfg.backend:
            voice_cfg = voice_cfg.model_copy(update={"backend": backend_override})

        try:
            if force and dest_path.exists():
                dest_path.unlink()
            get_backend(effective_backend).synthesize(text, voice_cfg, dest_path)
            generated += 1
            if output == OutputFormat.json:
                emit_progress(line_id, "generated", detail=f"{character} {i}/{total}")
        except Exception as exc:
            errors += 1
            if output == OutputFormat.text:
                print(f"  ERROR: {exc}", file=sys.stderr)
            else:
                emit_progress(line_id, "error", detail=str(exc))
            continue

        if effective_backend == "elevenlabs" and i < total:
            time.sleep(1.0)

    # Final checks
    missing_files = [e["id"] for e in script if not (voices_dir / f"{e['id']}.mp3").exists()]
    small_files = [
        e["id"]
        for e in script
        if (voices_dir / f"{e['id']}.mp3").exists()
        and (voices_dir / f"{e['id']}.mp3").stat().st_size < MIN_VALID_BYTES
    ]
    total_bytes = sum(
        (voices_dir / f"{e['id']}.mp3").stat().st_size
        for e in script
        if (voices_dir / f"{e['id']}.mp3").exists()
    )
    size_mb = round(total_bytes / 1024 / 1024, 2)

    if output == OutputFormat.text:
        print(f"\nGenerated: {generated}   Skipped: {skipped}   Errors: {errors}")
        print(f"Total voices size: {size_mb} MB")

    if missing_files:
        _die(
            cmd,
            output,
            code=ExitCode.PRECONDITION_FAILED,
            message=f"Missing voice files: {missing_files}",
            hint="Delete any partial files and rerun generate.",
        )
    if small_files:
        _die(
            cmd,
            output,
            code=ExitCode.UPSTREAM_ERROR,
            message=f"Voice files too small (likely partial): {small_files}",
            hint="Delete the listed files and rerun generate.",
        )
    if errors:
        _die(
            cmd,
            output,
            code=ExitCode.UPSTREAM_ERROR,
            message=f"{errors} voice line(s) failed to generate.",
            hint="Check the errors above and rerun.",
        )

    data = {"generated": generated, "skipped": skipped, "total": total, "size_mb": size_mb}
    if output == OutputFormat.text:
        print(f"All {total} voice lines present. Ready to assemble.")
    else:
        emit(success_envelope(cmd, data, start_time=t0), output)


# ---------------------------------------------------------------------------
# Command: assemble
# ---------------------------------------------------------------------------


@app.command("assemble")
def cmd_assemble(
    episode_dir: Path = typer.Option(
        Path("."),
        "--episode-dir",
        "-e",
        help="Episode directory containing episode.yaml and voices/.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate config and voice files without running ffmpeg."
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", "-o", help="Output format (text|json)."
    ),
) -> None:
    """Mix voice lines with background music and SFX into a final MP3."""
    t0 = time.time()
    cmd = "assemble"
    episode_dir = episode_dir.resolve()
    config = _load_config(episode_dir, cmd, output)

    # --- Dry run ---
    if dry_run:
        issues: list[str] = []
        if shutil.which("ffmpeg") is None:
            issues.append("ffmpeg not found on PATH")
        if shutil.which("ffprobe") is None:
            issues.append("ffprobe not found on PATH")

        voices_dir = episode_dir / "voices"
        voice_check = []
        for entry in config.timeline:
            p = voices_dir / f"{entry.id}.mp3"
            voice_check.append({"id": entry.id, "exists": p.exists(), "path": str(p)})

        bg_check = [
            {"file": bg.file, "exists": (episode_dir / bg.file).exists()} for bg in config.bg_tracks
        ]
        sfx_check = [
            {"file": sfx.file, "exists": (episode_dir / sfx.file).exists()}
            for sfx in config.sfx_hits
        ]

        missing_voices = [v["id"] for v in voice_check if not v["exists"]]
        if missing_voices:
            issues.append(f"Missing voice files: {missing_voices}")

        planned_actions = [
            {"step": "check_ffmpeg", "ok": shutil.which("ffmpeg") is not None},
            {"step": "check_voices", "missing": missing_voices},
            {
                "step": "bg_tracks",
                "present": sum(b["exists"] for b in bg_check),
                "missing": sum(not b["exists"] for b in bg_check),
            },
            {
                "step": "sfx_hits",
                "present": sum(s["exists"] for s in sfx_check),
                "missing": sum(not s["exists"] for s in sfx_check),
            },
        ]

        if output == OutputFormat.text:
            print(f"Dry run — assemble {episode_dir.name}")
            print(f"  ffmpeg:  {'ok' if shutil.which('ffmpeg') else 'MISSING'}")
            print(f"  voices:  {len(voice_check) - len(missing_voices)}/{len(voice_check)} present")
            print(f"  bg:      {sum(b['exists'] for b in bg_check)}/{len(bg_check)} present")
            print(f"  sfx:     {sum(s['exists'] for s in sfx_check)}/{len(sfx_check)} present")
            if issues:
                for issue in issues:
                    print(f"  ! {issue}", file=sys.stderr)
        else:
            emit(
                success_envelope(
                    cmd, {}, dry_run=True, planned_actions=planned_actions, start_time=t0
                ),
                output,
            )

        code = ExitCode.PRECONDITION_FAILED if issues else ExitCode.DRY_RUN
        raise typer.Exit(code)

    # --- Assemble ---
    log = print if output == OutputFormat.text else lambda *a, **kw: None
    try:
        result = assemble(episode_dir, config, log=log)
    except SystemExit as exc:
        _die(
            cmd,
            output,
            code=ExitCode.PRECONDITION_FAILED,
            message=str(exc),
            hint="Check the errors above.",
        )

    if output == OutputFormat.json:
        emit(success_envelope(cmd, result, start_time=t0), output)


# ---------------------------------------------------------------------------
# Command: introspect
# ---------------------------------------------------------------------------


@app.command("introspect", hidden=True)
def cmd_introspect(
    output: OutputFormat = typer.Option(
        OutputFormat.json, "--output", "-o", help="Output format (text|json)."
    ),
) -> None:
    """Output the full command tree as JSON for agent consumption."""
    tree = {
        "name": "podcastkit",
        "version": VERSION,
        "acli_version": "0.1.0",
        "commands": [
            {
                "name": "new",
                "description": "Create a new podcast project directory with episode stubs.",
                "idempotent": False,
                "arguments": [
                    {
                        "name": "name",
                        "required": True,
                        "description": "Project name (used as directory name).",
                    }
                ],
                "options": [
                    {
                        "name": "--episodes",
                        "short": "-n",
                        "type": "integer",
                        "default": 1,
                        "description": "Number of episode stubs to create.",
                    },
                    {
                        "name": "--dest",
                        "short": "-d",
                        "type": "path",
                        "default": ".",
                        "description": "Parent directory for the new project.",
                    },
                    {
                        "name": "--output",
                        "short": "-o",
                        "type": "enum[text|json]",
                        "default": "text",
                    },
                ],
                "examples": [
                    {
                        "description": "Create a single-episode project",
                        "invocation": "podcastkit new my-show",
                    },
                    {
                        "description": "Create a 6-episode project in ~/projects",
                        "invocation": "podcastkit new my-show --episodes 6 --dest ~/projects",
                    },
                ],
            },
            {
                "name": "generate",
                "description": "Synthesize voice lines via TTS and save them to voices/.",
                "idempotent": "conditional",
                "options": [
                    {
                        "name": "--episode-dir",
                        "short": "-e",
                        "type": "path",
                        "default": ".",
                        "description": "Episode directory containing episode.yaml and script.json.",
                    },
                    {
                        "name": "--backend",
                        "type": "enum[chatterbox|elevenlabs|kokoro|openai]",
                        "default": None,
                        "description": "Override TTS backend for all characters.",
                    },
                    {
                        "name": "--force",
                        "type": "bool",
                        "default": False,
                        "description": "Regenerate files even if they already exist.",
                    },
                    {
                        "name": "--dry-run",
                        "type": "bool",
                        "default": False,
                        "description": "Show what would be generated without calling any API.",
                    },
                    {
                        "name": "--output",
                        "short": "-o",
                        "type": "enum[text|json]",
                        "default": "text",
                    },
                ],
                "examples": [
                    {
                        "description": "Generate voices for the current episode directory",
                        "invocation": "podcastkit generate",
                    },
                    {
                        "description": "Generate using Kokoro (local, free) for episode_02",
                        "invocation": "podcastkit generate -e episode_02 --backend kokoro",
                    },
                    {
                        "description": "Preview what would be generated",
                        "invocation": "podcastkit generate --dry-run --output json",
                    },
                ],
                "see_also": ["assemble"],
            },
            {
                "name": "assemble",
                "description": "Mix voice lines with background music and SFX into a final MP3.",
                "idempotent": False,
                "options": [
                    {
                        "name": "--episode-dir",
                        "short": "-e",
                        "type": "path",
                        "default": ".",
                        "description": "Episode directory containing episode.yaml and voices/.",
                    },
                    {
                        "name": "--dry-run",
                        "type": "bool",
                        "default": False,
                        "description": "Validate config and voice files without running ffmpeg.",
                    },
                    {
                        "name": "--output",
                        "short": "-o",
                        "type": "enum[text|json]",
                        "default": "text",
                    },
                ],
                "examples": [
                    {
                        "description": "Assemble the current episode",
                        "invocation": "podcastkit assemble",
                    },
                    {
                        "description": "Assemble episode_01 and get JSON result",
                        "invocation": "podcastkit assemble --episode-dir episode_01 --output json",
                    },
                ],
                "see_also": ["generate"],
            },
            {
                "name": "introspect",
                "description": "Output the full command tree as JSON for agent consumption.",
                "idempotent": True,
                "hidden": True,
                "options": [
                    {
                        "name": "--output",
                        "short": "-o",
                        "type": "enum[text|json]",
                        "default": "json",
                    },
                ],
                "examples": [
                    {"description": "Dump command tree", "invocation": "podcastkit introspect"},
                    {
                        "description": "Dump command tree as JSON",
                        "invocation": "podcastkit introspect --output json",
                    },
                ],
            },
            {
                "name": "version",
                "description": "Show version information.",
                "idempotent": True,
                "hidden": True,
                "options": [
                    {
                        "name": "--output",
                        "short": "-o",
                        "type": "enum[text|json]",
                        "default": "text",
                    },
                ],
                "examples": [
                    {"description": "Show version", "invocation": "podcastkit version"},
                    {
                        "description": "Show version as JSON",
                        "invocation": "podcastkit version --output json",
                    },
                ],
            },
        ],
    }
    emit(success_envelope("introspect", tree, start_time=time.time()), output)


# ---------------------------------------------------------------------------
# Command: version
# ---------------------------------------------------------------------------


@app.command("version", hidden=True)
def cmd_version(
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", "-o", help="Output format (text|json)."
    ),
) -> None:
    """Show version information."""
    data = {"tool": "podcastkit", "version": VERSION, "acli_version": "0.1.0"}
    if output == OutputFormat.json:
        emit(success_envelope("version", data, start_time=time.time()), output)
    else:
        print(f"podcastkit {VERSION}")


# ---------------------------------------------------------------------------
# Subcommand group: write
# ---------------------------------------------------------------------------

write_app = typer.Typer(name="write", help="AI-assisted writing commands (bible, scripts).")
app.add_typer(write_app)

_WRITER_HELP = "LLM backend: claude | ollama | openai  [default: ollama]"
_MODEL_HELP = (
    "Model name (e.g. llama3.2, claude-opus-4-7, gpt-4o). Uses backend default if omitted."
)
_AI_CHARS_HELP = (
    "Comma-separated character names that are AI/robots and get 1.2s pre-silence. e.g. ARIA,HAL"
)


@write_app.command("bible")
def cmd_write_bible(
    concept: str = typer.Argument(..., help="One or more sentences describing the show concept."),
    episodes: int = typer.Option(6, "--episodes", "-n", help="Number of episodes to plan."),
    writer: str = typer.Option("ollama", "--writer", "-w", help=_WRITER_HELP),
    model: str | None = typer.Option(None, "--model", "-m", help=_MODEL_HELP),
    output_file: Path = typer.Option(
        Path("bible.md"), "--output", "-o", help="Where to write the bible Markdown."
    ),
    fmt: OutputFormat = typer.Option(
        OutputFormat.text, "--format", "-f", help="Terminal output format (text|json)."
    ),
) -> None:
    """Generate a series bible from a concept using an LLM."""
    t0 = time.time()
    cmd = "write bible"

    try:
        w = get_writer(writer, model)
    except ValueError as exc:
        _die(cmd, fmt, code=ExitCode.INVALID_ARGS, message=str(exc))

    system, user = build_bible_prompts(concept, episodes)

    if fmt == OutputFormat.text:
        print(f"Generating series bible with {writer}…")

    try:
        bible_text = w.complete(system, user)
    except RuntimeError as exc:
        _die(
            cmd,
            fmt,
            code=ExitCode.UPSTREAM_ERROR,
            message=str(exc),
            hint="Check that your LLM backend is reachable and credentials are set.",
        )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(bible_text, encoding="utf-8")

    data = {"output": str(output_file), "length_chars": len(bible_text)}
    if fmt == OutputFormat.text:
        print(f"Bible written to {output_file}  ({len(bible_text)} chars)")
    else:
        emit(success_envelope(cmd, data, start_time=t0), fmt)


@write_app.command("script")
def cmd_write_script(
    bible: Path = typer.Option(
        ..., "--bible", "-b", help="Path to the series bible Markdown file."
    ),
    episode: int = typer.Option(..., "--episode", "-e", help="Episode number to write."),
    summary: str = typer.Option(
        "", "--summary", "-s", help="Episode summary. If omitted, the LLM infers it from the bible."
    ),
    title: str = typer.Option("", "--title", "-t", help="Episode title (optional)."),
    lines: int = typer.Option(60, "--lines", "-l", help="Target number of script lines."),
    episode_dir: Path = typer.Option(
        Path("."), "--episode-dir", "-d", help="Directory to write script.json and episode.yaml."
    ),
    ai_characters: str = typer.Option("", "--ai-chars", help=_AI_CHARS_HELP),
    writer: str = typer.Option("ollama", "--writer", "-w", help=_WRITER_HELP),
    model: str | None = typer.Option(None, "--model", "-m", help=_MODEL_HELP),
    fmt: OutputFormat = typer.Option(
        OutputFormat.text, "--format", "-f", help="Terminal output format (text|json)."
    ),
) -> None:
    """Generate a script.json (and episode.yaml stub) from a bible using an LLM."""
    t0 = time.time()
    cmd = "write script"

    if not bible.exists():
        _die(
            cmd,
            fmt,
            code=ExitCode.NOT_FOUND,
            message=f"Bible file not found: {bible}",
            hint="Run 'podcastkit write bible' first.",
        )

    try:
        w = get_writer(writer, model)
    except ValueError as exc:
        _die(cmd, fmt, code=ExitCode.INVALID_ARGS, message=str(exc))

    bible_text = bible.read_text(encoding="utf-8")
    system, user = build_script_prompts(bible_text, episode, summary, title, lines)

    if fmt == OutputFormat.text:
        print(f"Generating episode {episode} script with {writer}…")

    MAX_RETRIES = 3
    script: list[dict] = []
    last_err = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw = w.complete(system, user)
            entries = extract_json(raw)
            script = normalize_script(entries)
            break
        except (ValueError, Exception) as exc:
            last_err = str(exc)
            if fmt == OutputFormat.text:
                print(f"  attempt {attempt} failed: {last_err[:120]}")
            if attempt == MAX_RETRIES:
                _die(
                    cmd,
                    fmt,
                    code=ExitCode.UPSTREAM_ERROR,
                    message=f"Failed to get valid JSON after {MAX_RETRIES} attempts: {last_err}",
                    hint="Try a larger model or add --summary to give the LLM more context.",
                )

    # Write script.json
    episode_dir.mkdir(parents=True, exist_ok=True)
    script_path = episode_dir / "script.json"
    script_path.write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")

    # Write episode.yaml stub if it doesn't already exist
    yaml_path = episode_dir / "episode.yaml"
    if not yaml_path.exists():
        ai_chars_set = {c.strip().upper() for c in ai_characters.split(",") if c.strip()}
        timeline = derive_timeline(script, ai_chars_set)
        voices = derive_voices_stub(script)
        ep_title = title or f"Episode {episode}"
        stub = {
            "title": ep_title,
            "output": f"episode_{episode:02d}.mp3",
            "voices": voices,
            "timeline": timeline,
            "bg_tracks": [],
            "sfx_hits": [],
        }
        yaml_path.write_text(
            yaml.dump(stub, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
        yaml_written = True
    else:
        yaml_written = False

    data = {
        "script": str(script_path),
        "lines": len(script),
        "characters": sorted({e["character"] for e in script}),
        "episode_yaml": str(yaml_path) if yaml_written else None,
    }

    if fmt == OutputFormat.text:
        chars = ", ".join(data["characters"])
        n_chars = len(data["characters"])
        print(f"script.json written  ({len(script)} lines, {n_chars} characters: {chars})")
        if yaml_written:
            print("episode.yaml stub written — fill in voice_ids before running generate")
    else:
        emit(success_envelope(cmd, data, start_time=t0), fmt)


# ---------------------------------------------------------------------------
# Subcommand group: sfx
# ---------------------------------------------------------------------------

sfx_app = typer.Typer(
    name="sfx", help="Generate sound effects and music via MusicGen (local, no API key)."
)
app.add_typer(sfx_app)

_AUDIOGEN_MODEL_HELP = (
    "MusicGen model for SFX. Options: facebook/musicgen-small (default), facebook/musicgen-medium."
)
_MUSICGEN_MODEL_HELP = (
    "MusicGen model. Options: facebook/musicgen-small (default), "
    "facebook/musicgen-medium, facebook/musicgen-large, facebook/musicgen-stereo-small."
)
_DEVICE_HELP = "Compute device: cuda | mps | cpu. Auto-detected from hardware if omitted."


@sfx_app.command("generate")
def cmd_sfx_generate(
    prompt: str = typer.Argument(..., help="Text description of the sound effect to generate."),
    output: Path = typer.Option(..., "--output", "-o", help="Destination WAV file path."),
    duration: float = typer.Option(
        3.0, "--duration", "-d", help="Length of generated audio in seconds."
    ),
    model: str = typer.Option(
        "facebook/musicgen-small", "--model", "-m", help=_AUDIOGEN_MODEL_HELP
    ),
    device: str | None = typer.Option(None, "--device", help=_DEVICE_HELP),
    fmt: OutputFormat = typer.Option(
        OutputFormat.text, "--format", "-f", help="Terminal output format (text|json)."
    ),
) -> None:
    """Generate a sound effect from a text prompt using AudioGen (open-source, local)."""
    t0 = time.time()
    cmd = "sfx generate"
    log = print if fmt == OutputFormat.text else lambda *a, **kw: None

    try:
        result = generate_sfx(
            prompt,
            output.resolve(),
            duration=duration,
            model_name=model,
            device=device,
            log=log,
        )
    except RuntimeError as exc:
        _die(
            cmd,
            fmt,
            code=ExitCode.UPSTREAM_ERROR,
            message=str(exc),
            hint="Install AudioCraft: pip install 'podcastkit[audiocraft]'",
        )

    if fmt == OutputFormat.text:
        print(
            f"SFX saved to {result['path']}  ({result['duration_s']}s @ {result['sample_rate']} Hz)"
        )
    else:
        emit(success_envelope(cmd, result, start_time=t0), fmt)


@sfx_app.command("music")
def cmd_sfx_music(
    prompt: str = typer.Argument(..., help="Text description of the background music to generate."),
    output: Path = typer.Option(..., "--output", "-o", help="Destination WAV file path."),
    duration: float = typer.Option(
        30.0, "--duration", "-d", help="Length of generated audio in seconds."
    ),
    model: str = typer.Option(
        "facebook/musicgen-small", "--model", "-m", help=_MUSICGEN_MODEL_HELP
    ),
    device: str | None = typer.Option(None, "--device", help=_DEVICE_HELP),
    fmt: OutputFormat = typer.Option(
        OutputFormat.text, "--format", "-f", help="Terminal output format (text|json)."
    ),
) -> None:
    """Generate background music from a text prompt using MusicGen (open-source, local)."""
    t0 = time.time()
    cmd = "sfx music"
    log = print if fmt == OutputFormat.text else lambda *a, **kw: None

    try:
        result = generate_music(
            prompt,
            output.resolve(),
            duration=duration,
            model_name=model,
            device=device,
            log=log,
        )
    except RuntimeError as exc:
        _die(
            cmd,
            fmt,
            code=ExitCode.UPSTREAM_ERROR,
            message=str(exc),
            hint="Install AudioCraft: pip install 'podcastkit[audiocraft]'",
        )

    if fmt == OutputFormat.text:
        print(
            f"Music saved to {result['path']}  ({result['duration_s']}s @ {result['sample_rate']} Hz)"  # noqa: E501
        )
    else:
        emit(success_envelope(cmd, result, start_time=t0), fmt)
