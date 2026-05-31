from __future__ import annotations

import re
import time
from pathlib import Path

import typer
import yaml

from ._context import (
    assemble_recap,
    bible_to_prompt_text,
    find_chapter_file,
    prev_chapter_text,
)
from ._errors import BookKitError
from ._exit_codes import ExitCode
from ._extract import split_prose_and_yaml
from ._output import (
    OutputFormat,
    emit,
    error_envelope,
    success_envelope,
)
from .bible import Beat, BibleConfig, StateChange, dump_bible, load_bible
from .bind import bind
from .config import BookConfig
from .prompts import build_chapter_prompts, build_outline_prompts, build_recap_prompts
from .renderers import VALID_FORMATS
from .scaffold import scaffold_book
from .writers import default_writer_name, get_writer

VERSION = "0.1.0"

app = typer.Typer(
    name="bookkit",
    help="CLI for producing books as code — Markdown chapters rendered to EPUB and PDF.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _load_config(book_dir: Path, cmd: str, fmt: OutputFormat) -> BookConfig:
    yaml_path = book_dir / "book.yaml"
    if not yaml_path.exists():
        _die(
            cmd,
            fmt,
            code=ExitCode.NOT_FOUND,
            message=f"book.yaml not found in {book_dir}",
            hint="Run 'bookkit new <title>' to scaffold a book first.",
        )
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return BookConfig.model_validate(raw)


# ---------------------------------------------------------------------------
# Command: new
# ---------------------------------------------------------------------------


@app.command("new")
def cmd_new(
    title: str = typer.Argument(..., help="Book title (also used as the directory name)."),
    chapters: int = typer.Option(1, "--chapters", "-n", help="Number of chapter stubs to create."),
    dest: Path = typer.Option(Path("."), "--dest", "-d", help="Parent directory for the new book."),
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", "-o", help="Output format (text|json)."
    ),
) -> None:
    """Create a new book directory with a book.yaml and chapter stubs."""
    t0 = time.time()
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "book"
    book_dir = dest.resolve() / slug
    chapter_files = scaffold_book(title, book_dir, num_chapters=chapters)

    data = {
        "book": title,
        "path": str(book_dir),
        "chapters": chapter_files,
    }
    if output == OutputFormat.text:
        print(f"Created book '{title}' at {book_dir}")
        print("  book.yaml")
        for ch in chapter_files:
            print(f"  {ch}")
    else:
        emit(success_envelope("new", data, start_time=t0), output)


# ---------------------------------------------------------------------------
# Command: build
# ---------------------------------------------------------------------------


@app.command("build")
def cmd_build(
    book_dir: Path = typer.Option(
        Path("."), "--book-dir", "-b", help="Book directory containing book.yaml."
    ),
    fmt: str = typer.Option(
        "epub", "--format", "-f", help=f"Output format ({'|'.join(VALID_FORMATS)})."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate the book and show the plan without rendering."
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", "-o", help="Output format (text|json)."
    ),
) -> None:
    """Render the book's Markdown chapters into a single EPUB/PDF/HTML artifact."""
    t0 = time.time()
    cmd = "build"
    book_dir = book_dir.resolve()

    if fmt not in VALID_FORMATS:
        _die(
            cmd,
            output,
            code=ExitCode.INVALID_ARGS,
            message=f"Unknown format: {fmt!r}",
            hint=f"Valid formats are: {', '.join(VALID_FORMATS)}.",
        )

    config = _load_config(book_dir, cmd, output)

    # Verify every chapter source exists before doing any work.
    missing = [c.file for c in config.chapters if not (book_dir / c.file).exists()]
    if missing:
        _die(
            cmd,
            output,
            code=ExitCode.PRECONDITION_FAILED,
            message=f"{len(missing)} chapter file(s) missing",
            hints=[f"missing: {m}" for m in missing],
        )

    if dry_run:
        from .bind import output_path

        planned = [
            {
                "format": fmt,
                "chapters": len(config.chapters),
                "output": str(output_path(config, book_dir, fmt)),
            }
        ]
        envelope = success_envelope(cmd, {}, start_time=t0, dry_run=True, planned_actions=planned)
        emit(envelope, output)
        raise typer.Exit(code=ExitCode.DRY_RUN)

    try:
        data = bind(config, book_dir, fmt)
    except BookKitError as exc:
        _die(cmd, output, code=exc.code, message=str(exc), hint=exc.hint, hints=exc.hints)
    except RuntimeError as exc:
        _die(
            cmd,
            output,
            code=ExitCode.UPSTREAM_ERROR,
            message=str(exc),
            hint="Install the matching extra, e.g. pip install 'bookkit[pdf]'.",
        )

    if output == OutputFormat.text:
        print(f"Built {data['output']}")
        print(f"  format:   {data['format']}")
        print(f"  chapters: {data['chapters']}")
        print(f"  words:    {data['words']}")
        print(f"  pages:    ~{data['est_pages']}")
        print(f"  size:     {data['size_mb']} MB")
    else:
        emit(success_envelope(cmd, data, start_time=t0), output)


# ---------------------------------------------------------------------------
# Command group: write (AI-assisted)
# ---------------------------------------------------------------------------

write_app = typer.Typer(name="write", help="AI-assisted writing commands (outline, chapters).")
app.add_typer(write_app)


@write_app.command("outline")
def cmd_write_outline(
    concept: str = typer.Argument(..., help="One or more sentences describing the book."),
    chapters: int = typer.Option(
        10, "--chapters", "-n", help="Target number of chapters in the outline."
    ),
    writer: str | None = typer.Option(
        None,
        "--writer",
        "-w",
        help="LLM backend (claude|ollama|openai|openai_compat). "
        "Default: $BOOKKIT_WRITER, else ollama.",
    ),
    model: str | None = typer.Option(
        None, "--model", "-m", help="Override the model name (else $BOOKKIT_MODEL)."
    ),
    out: Path = typer.Option(
        Path("outline.md"), "--output", "-o", help="Path to write the prose outline."
    ),
    bible_out: Path = typer.Option(
        Path("bible.yaml"), "--bible", help="Path to write the structured bible (canon)."
    ),
) -> None:
    """Generate a prose outline AND a structured bible.yaml (canon) from a concept."""
    cmd = "write outline"
    writer_name = writer or default_writer_name()
    system, user = build_outline_prompts(concept, chapters)
    try:
        text = get_writer(writer_name, model).complete(system, user)
    except (RuntimeError, ValueError) as exc:
        _die(cmd, OutputFormat.text, code=ExitCode.UPSTREAM_ERROR, message=str(exc))

    prose, yaml_block = split_prose_and_yaml(text)
    out.write_text(prose + "\n", encoding="utf-8")

    # Parse the structured canon defensively; fall back to a minimal valid stub so a
    # weaker model that skipped (or malformed) the YAML never blocks the workflow.
    bible: BibleConfig
    bible_note = "parsed from model output"
    if yaml_block:
        try:
            bible = BibleConfig.model_validate(yaml.safe_load(yaml_block) or {})
        except Exception:
            bible = BibleConfig(beats=[{"chapter": i} for i in range(1, chapters + 1)])
            bible_note = "model YAML invalid — wrote a stub to fill in"
    else:
        bible = BibleConfig(beats=[{"chapter": i} for i in range(1, chapters + 1)])
        bible_note = "model emitted no YAML — wrote a stub to fill in"
    bible_out.write_text(dump_bible(bible), encoding="utf-8")

    print(f"Wrote outline to {out} ({len(prose)} chars)")
    print(
        f"Wrote bible to {bible_out} ({len(bible.characters)} characters, "
        f"{len(bible.beats)} beats) — {bible_note}"
    )


@write_app.command("chapter")
def cmd_write_chapter(
    outline: Path = typer.Option(..., "--outline", help="Path to the outline Markdown file."),
    chapter: int = typer.Option(..., "--chapter", "-c", help="Chapter number to write."),
    summary: str = typer.Option("", "--summary", "-s", help="Optional summary for this chapter."),
    title: str = typer.Option("", "--title", "-t", help="Optional chapter title."),
    words: int = typer.Option(2000, "--words", help="Target word count."),
    book_dir: Path = typer.Option(
        Path("."), "--book-dir", "-b", help="Book dir (for bible.yaml, recaps/, chapters/)."
    ),
    bible_path: Path = typer.Option(
        None, "--bible", help="Path to bible.yaml (default: <book-dir>/bible.yaml)."
    ),
    use_recap: bool = typer.Option(
        True, "--recap/--no-recap", help="Include a recap of earlier chapters as context."
    ),
    prev_full: bool = typer.Option(
        True, "--prev-full/--no-prev-full", help="Include the previous chapter's full text."
    ),
    writer: str | None = typer.Option(
        None,
        "--writer",
        "-w",
        help="LLM backend (claude|ollama|openai|openai_compat). "
        "Default: $BOOKKIT_WRITER, else ollama.",
    ),
    model: str | None = typer.Option(
        None, "--model", "-m", help="Override the model name (else $BOOKKIT_MODEL)."
    ),
    out: Path = typer.Option(
        None, "--output", "-o", help="Output path (default: <book-dir>/chapters/NN-*.md)."
    ),
) -> None:
    """Generate a chapter's prose from an outline, with canon + story-so-far context."""
    cmd = "write chapter"
    writer_name = writer or default_writer_name()
    if not outline.exists():
        _die(
            cmd, OutputFormat.text, code=ExitCode.NOT_FOUND, message=f"outline not found: {outline}"
        )
    outline_text = outline.read_text(encoding="utf-8")
    book_dir = book_dir.resolve()

    # Continuity layers (all optional; degrade gracefully if absent).
    canon = ""
    beat_summary = summary
    bible_file = bible_path or (book_dir / "bible.yaml")
    sources_used = []
    if bible_file.exists():
        bible = load_bible(bible_file)
        canon = bible_to_prompt_text(bible, upto_chapter=chapter)
        beat = bible.beat_for(chapter)
        if beat and not summary:
            beat_summary = beat.summary
        if canon:
            sources_used.append("bible")
    recap = assemble_recap(book_dir, chapter) if use_recap else ""
    if recap:
        sources_used.append("recap")
    prev = prev_chapter_text(book_dir, chapter) if prev_full else ""
    if prev:
        sources_used.append("prev-chapter")

    system, user = build_chapter_prompts(
        outline_text,
        chapter,
        beat_summary,
        title,
        words,
        canon=canon,
        recap=recap,
        prev_chapter=prev,
    )
    try:
        text = get_writer(writer_name, model).complete(system, user)
    except (RuntimeError, ValueError) as exc:
        _die(cmd, OutputFormat.text, code=ExitCode.UPSTREAM_ERROR, message=str(exc))

    dest = out or book_dir / "chapters" / f"{chapter:02d}-chapter.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text.strip() + "\n", encoding="utf-8")
    context_note = ", ".join(sources_used) if sources_used else "no continuity context found"
    print(f"Wrote chapter {chapter} to {dest} ({len(text)} chars) — context: {context_note}")


@app.command("recap")
def cmd_recap(
    chapter: int = typer.Option(..., "--chapter", "-c", help="Chapter number to recap."),
    book_dir: Path = typer.Option(
        Path("."), "--book-dir", "-b", help="Book dir (for chapters/, recaps/, bible.yaml)."
    ),
    apply: bool = typer.Option(
        False, "--apply", help="Apply proposed state changes to bible.yaml."
    ),
    writer: str | None = typer.Option(
        None, "--writer", "-w", help="LLM backend. Default: $BOOKKIT_WRITER, else ollama."
    ),
    model: str | None = typer.Option(
        None, "--model", "-m", help="Override the model name (else $BOOKKIT_MODEL)."
    ),
) -> None:
    """Summarize a chapter into recaps/NN.md and propose canonical state changes."""
    cmd = "recap"
    writer_name = writer or default_writer_name()
    book_dir = book_dir.resolve()

    chapter_file = find_chapter_file(book_dir, chapter)
    if not chapter_file:
        _die(
            cmd,
            OutputFormat.text,
            code=ExitCode.NOT_FOUND,
            message=f"chapter {chapter} source not found under {book_dir}",
            hint="Write the chapter first (bookkit write chapter -c N).",
        )
    chapter_text = chapter_file.read_text(encoding="utf-8")

    system, user = build_recap_prompts(chapter, chapter_text)
    try:
        response = get_writer(writer_name, model).complete(system, user)
    except (RuntimeError, ValueError) as exc:
        _die(cmd, OutputFormat.text, code=ExitCode.UPSTREAM_ERROR, message=str(exc))

    prose, yaml_block = split_prose_and_yaml(response)
    recaps_dir = book_dir / "recaps"
    recaps_dir.mkdir(parents=True, exist_ok=True)
    recap_path = recaps_dir / f"{chapter:02d}.md"
    recap_path.write_text(prose + "\n", encoding="utf-8")
    print(f"Wrote recap to {recap_path} ({len(prose)} chars)")

    # Parse and report (optionally apply) proposed canonical state changes.
    changes: list[StateChange] = []
    if yaml_block:
        try:
            parsed = yaml.safe_load(yaml_block) or {}
            beat = Beat.model_validate({"chapter": chapter, **parsed})
            changes = beat.state_changes
        except Exception:
            changes = []
    if not changes:
        print("No canonical state changes proposed.")
        return
    print(f"Proposed state changes for chapter {chapter}:")
    for c in changes:
        print(f"  - {c.character + ': ' if c.character else ''}{c.set or c.note}")
    bible_file = book_dir / "bible.yaml"
    if apply and bible_file.exists():
        bible = load_bible(bible_file)
        bible.apply_state_changes(chapter, changes)
        bible_file.write_text(dump_bible(bible), encoding="utf-8")
        print(f"Applied {len(changes)} change(s) to {bible_file}")
    elif apply:
        print(f"--apply set but {bible_file} not found; nothing applied.")
    else:
        print("Re-run with --apply to write these into bible.yaml.")


# ---------------------------------------------------------------------------
# Command: introspect (agent discovery)
# ---------------------------------------------------------------------------


@app.command("introspect", hidden=True)
def cmd_introspect(
    output: OutputFormat = typer.Option(
        OutputFormat.json, "--output", "-o", help="Output format (text|json)."
    ),
) -> None:
    """Output the full command tree as JSON for agent consumption."""
    tree = {
        "name": "bookkit",
        "version": VERSION,
        "acli_version": "0.1.0",
        "commands": [
            {
                "name": "new",
                "description": "Create a new book directory with a book.yaml and chapter stubs.",
                "idempotent": False,
                "arguments": [{"name": "title", "required": True, "description": "Book title."}],
                "options": [
                    {"name": "--chapters", "short": "-n", "type": "integer", "default": 1},
                    {"name": "--dest", "short": "-d", "type": "path", "default": "."},
                    {
                        "name": "--output",
                        "short": "-o",
                        "type": "enum[text|json]",
                        "default": "text",
                    },
                ],
                "examples": [
                    {
                        "description": "Scaffold a 12-chapter book",
                        "invocation": "bookkit new 'My Book' -n 12",
                    }
                ],
            },
            {
                "name": "build",
                "description": "Render Markdown chapters into a single EPUB/PDF/HTML artifact.",
                "idempotent": True,
                "options": [
                    {"name": "--book-dir", "short": "-b", "type": "path", "default": "."},
                    {
                        "name": "--format",
                        "short": "-f",
                        "type": "enum[epub|pdf|html]",
                        "default": "epub",
                    },
                    {"name": "--dry-run", "type": "bool", "default": False},
                    {
                        "name": "--output",
                        "short": "-o",
                        "type": "enum[text|json]",
                        "default": "text",
                    },
                ],
                "examples": [
                    {"description": "Build an EPUB", "invocation": "bookkit build -f epub"},
                    {"description": "Build a PDF", "invocation": "bookkit build -f pdf"},
                ],
            },
            {
                "name": "write outline",
                "description": "Generate a book outline from a concept using an LLM.",
                "idempotent": False,
                "arguments": [
                    {"name": "concept", "required": True, "description": "Book concept."}
                ],
                "options": [
                    {"name": "--chapters", "short": "-n", "type": "integer", "default": 10},
                    {
                        "name": "--writer",
                        "short": "-w",
                        "type": "enum[claude|ollama|openai]",
                        "default": "ollama",
                    },
                    {"name": "--model", "short": "-m", "type": "string", "default": None},
                    {"name": "--output", "short": "-o", "type": "path", "default": "outline.md"},
                ],
            },
            {
                "name": "write chapter",
                "description": "Generate a chapter's prose from an outline, with canon "
                "+ story-so-far continuity context, using an LLM.",
                "idempotent": False,
                "options": [
                    {"name": "--outline", "type": "path", "required": True},
                    {"name": "--chapter", "short": "-c", "type": "integer", "required": True},
                    {"name": "--summary", "short": "-s", "type": "string", "default": ""},
                    {"name": "--title", "short": "-t", "type": "string", "default": ""},
                    {"name": "--words", "type": "integer", "default": 2000},
                    {"name": "--book-dir", "short": "-b", "type": "path", "default": "."},
                    {"name": "--bible", "type": "path", "default": "<book-dir>/bible.yaml"},
                    {"name": "--recap/--no-recap", "type": "bool", "default": True},
                    {"name": "--prev-full/--no-prev-full", "type": "bool", "default": True},
                    {
                        "name": "--writer",
                        "short": "-w",
                        "type": "enum[claude|ollama|openai|openai_compat]",
                        "default": "$BOOKKIT_WRITER|ollama",
                    },
                    {"name": "--model", "short": "-m", "type": "string", "default": None},
                    {"name": "--output", "short": "-o", "type": "path", "default": None},
                ],
            },
            {
                "name": "recap",
                "description": "Summarize a chapter into recaps/NN.md and propose "
                "canonical state changes for the bible.",
                "idempotent": True,
                "options": [
                    {"name": "--chapter", "short": "-c", "type": "integer", "required": True},
                    {"name": "--book-dir", "short": "-b", "type": "path", "default": "."},
                    {"name": "--apply", "type": "bool", "default": False},
                    {
                        "name": "--writer",
                        "short": "-w",
                        "type": "enum[claude|ollama|openai|openai_compat]",
                        "default": "$BOOKKIT_WRITER|ollama",
                    },
                    {"name": "--model", "short": "-m", "type": "string", "default": None},
                ],
            },
        ],
    }
    emit(success_envelope("introspect", tree, start_time=time.time()), output)


@app.command("version", hidden=True)
def cmd_version(
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", "-o", help="Output format (text|json)."
    ),
) -> None:
    """Print the bookkit version."""
    if output == OutputFormat.text:
        print(VERSION)
    else:
        emit(success_envelope("version", {"version": VERSION}, start_time=time.time()), output)


if __name__ == "__main__":
    app()
