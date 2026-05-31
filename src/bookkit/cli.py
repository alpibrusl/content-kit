from __future__ import annotations

import re
import time
from pathlib import Path

import typer
import yaml

from ._errors import BookKitError
from ._exit_codes import ExitCode
from ._output import (
    OutputFormat,
    emit,
    error_envelope,
    success_envelope,
)
from .bind import bind
from .config import BookConfig
from .prompts import build_chapter_prompts, build_outline_prompts
from .renderers import VALID_FORMATS
from .scaffold import scaffold_book
from .writers import get_writer

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
    writer: str = typer.Option(
        "ollama", "--writer", "-w", help="LLM backend (claude|ollama|openai)."
    ),
    model: str | None = typer.Option(None, "--model", "-m", help="Override the model name."),
    out: Path = typer.Option(
        Path("outline.md"), "--output", "-o", help="Path to write the outline."
    ),
) -> None:
    """Generate a book outline (the 'bible') from a concept."""
    system, user = build_outline_prompts(concept, chapters)
    try:
        text = get_writer(writer, model).complete(system, user)
    except (RuntimeError, ValueError) as exc:
        _die("write outline", OutputFormat.text, code=ExitCode.UPSTREAM_ERROR, message=str(exc))
    out.write_text(text.strip() + "\n", encoding="utf-8")
    print(f"Wrote outline to {out} ({len(text)} chars)")


@write_app.command("chapter")
def cmd_write_chapter(
    outline: Path = typer.Option(..., "--outline", help="Path to the outline Markdown file."),
    chapter: int = typer.Option(..., "--chapter", "-c", help="Chapter number to write."),
    summary: str = typer.Option("", "--summary", "-s", help="Optional summary for this chapter."),
    title: str = typer.Option("", "--title", "-t", help="Optional chapter title."),
    words: int = typer.Option(2000, "--words", help="Target word count."),
    writer: str = typer.Option(
        "ollama", "--writer", "-w", help="LLM backend (claude|ollama|openai)."
    ),
    model: str | None = typer.Option(None, "--model", "-m", help="Override the model name."),
    out: Path = typer.Option(
        None, "--output", "-o", help="Output path (default: chapters/NN-*.md)."
    ),
) -> None:
    """Generate a chapter's prose from an outline."""
    cmd = "write chapter"
    if not outline.exists():
        _die(
            cmd, OutputFormat.text, code=ExitCode.NOT_FOUND, message=f"outline not found: {outline}"
        )
    outline_text = outline.read_text(encoding="utf-8")

    system, user = build_chapter_prompts(outline_text, chapter, summary, title, words)
    try:
        text = get_writer(writer, model).complete(system, user)
    except (RuntimeError, ValueError) as exc:
        _die(cmd, OutputFormat.text, code=ExitCode.UPSTREAM_ERROR, message=str(exc))

    dest = out or Path("chapters") / f"{chapter:02d}-chapter.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text.strip() + "\n", encoding="utf-8")
    print(f"Wrote chapter {chapter} to {dest} ({len(text)} chars)")


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
                "description": "Generate a chapter's prose from an outline using an LLM.",
                "idempotent": False,
                "options": [
                    {"name": "--outline", "type": "path", "required": True},
                    {"name": "--chapter", "short": "-c", "type": "integer", "required": True},
                    {"name": "--summary", "short": "-s", "type": "string", "default": ""},
                    {"name": "--title", "short": "-t", "type": "string", "default": ""},
                    {"name": "--words", "type": "integer", "default": 2000},
                    {
                        "name": "--writer",
                        "short": "-w",
                        "type": "enum[claude|ollama|openai]",
                        "default": "ollama",
                    },
                    {"name": "--model", "short": "-m", "type": "string", "default": None},
                    {"name": "--output", "short": "-o", "type": "path", "default": None},
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
