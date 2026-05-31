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
from .continuity import check_book, check_series
from .prompts import (
    build_chapter_prompts,
    build_continuity_prompts,
    build_outline_prompts,
    build_recap_prompts,
)
from .renderers import VALID_FORMATS
from .scaffold import scaffold_book, scaffold_series
from .series import load_series, merge_shared_characters, series_context_text
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
# Command: audiobook (bridge to podcastkit)
# ---------------------------------------------------------------------------


@app.command("audiobook")
def cmd_audiobook(
    book_dir: Path = typer.Option(
        Path("."), "--book-dir", "-b", help="Book directory containing book.yaml."
    ),
    dest: Path = typer.Option(
        None,
        "--dest",
        "-d",
        help="Where to write the podcastkit project (default: <book-dir>/<slug>-audiobook).",
    ),
    backend: str = typer.Option(
        "kokoro",
        "--backend",
        help="TTS backend for the narrator voice (kokoro|chatterbox|openai|elevenlabs).",
    ),
    voice: str = typer.Option(
        "bm_george", "--voice", help="Narrator voice id for the chosen backend."
    ),
    narrator: str = typer.Option("NARRATOR", "--narrator", help="Name of the narration character."),
    max_chars: int = typer.Option(
        600, "--max-chars", help="Maximum characters per narration line (TTS chunk size)."
    ),
    cast: bool = typer.Option(
        False,
        "--cast",
        help="Full-cast reading: attribute dialogue to bible characters (else single narrator).",
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing script.json/episode.yaml files."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show the plan (episodes, lines, characters) without writing."
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", "-o", help="Output format (text|json)."
    ),
) -> None:
    """Convert a book into a podcastkit project (script.json + episode.yaml per chapter).

    Reads the book's Markdown chapters and, when present, its bible.yaml — whose
    cast becomes the audiobook's voice cast — and emits a podcastkit-ready project.
    Render it with: ``podcastkit generate -e <dir>/chapter_NN`` then
    ``podcastkit assemble -e <dir>/chapter_NN``.
    """
    from .audiobook import plan_audiobook, slugify, write_project

    t0 = time.time()
    cmd = "audiobook"
    book_dir = book_dir.resolve()
    config = _load_config(book_dir, cmd, output)

    missing = [c.file for c in config.chapters if not (book_dir / c.file).exists()]
    if missing:
        _die(
            cmd,
            output,
            code=ExitCode.PRECONDITION_FAILED,
            message=f"{len(missing)} chapter file(s) missing",
            hints=[f"missing: {m}" for m in missing],
        )

    bible_file = book_dir / "bible.yaml"
    bible = load_bible(bible_file) if bible_file.exists() else None

    plan = plan_audiobook(
        config,
        book_dir,
        bible=bible,
        backend=backend,
        voice_id=voice,
        narrator=narrator,
        max_chars=max_chars,
        cast=cast,
    )
    target = (dest or (book_dir / f"{slugify(config.title)}-audiobook")).resolve()

    if dry_run:
        planned = [
            {
                "episode": ep.name,
                "title": ep.title,
                "lines": len(ep.script),
                "chars": ep.char_count,
            }
            for ep in plan.episodes
        ]
        envelope = success_envelope(cmd, {}, start_time=t0, dry_run=True, planned_actions=planned)
        emit(envelope, output)
        raise typer.Exit(code=ExitCode.DRY_RUN)

    written = write_project(plan, target, force=force)

    data = {
        "project": str(target),
        "episodes": len(plan.episodes),
        "lines": plan.line_count,
        "characters": len(plan.voices),
        "chars": plan.char_count,
        "narrator_backend": backend,
        "cast": cast,
        "cast_lines": plan.cast_line_count,
        "files_written": len(written),
    }
    if output == OutputFormat.text:
        print(f"Wrote audiobook project to {target}")
        print(f"  episodes:   {data['episodes']} (one per chapter)")
        print(f"  lines:      {data['lines']}")
        print(f"  characters: {data['characters']} (cast from bible.yaml + narrator)")
        if cast:
            print(
                f"  cast lines: {data['cast_lines']} dialogue line(s) "
                "attributed to characters (rest narrated)"
            )
        print(f"  chars:      {data['chars']} (TTS billing estimate for paid backends)")
        print(f"  files:      {data['files_written']} written")
        if written:
            print(
                f"  next:       podcastkit generate -e {target.name}/chapter_01 "
                f"&& podcastkit assemble -e {target.name}/chapter_01"
            )
    else:
        emit(success_envelope(cmd, data, start_time=t0), output)


# ---------------------------------------------------------------------------
# Command: storyboard (visual tier — comic / video script)
# ---------------------------------------------------------------------------


@app.command("storyboard")
def cmd_storyboard(
    book_dir: Path = typer.Option(
        Path("."), "--book-dir", "-b", help="Book directory containing book.yaml."
    ),
    dest: Path = typer.Option(
        None,
        "--dest",
        "-d",
        help="Where to write the storyboard (default: <book-dir>/<slug>-storyboard).",
    ),
    max_panel_chars: int = typer.Option(
        320, "--max-panel-chars", help="Maximum characters of prose per panel."
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing storyboard.json files."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show the plan (chapters, panels) without writing."
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", "-o", help="Output format (text|json)."
    ),
) -> None:
    """Generate a storyboard (panel/shot script) from a book — the visual tier.

    Emits one storyboard.json per chapter: ordered panels with a scene
    description, attributed dialogue, and the characters present (with art notes
    pulled from bible.yaml). A comic or video tool renders the panels; bookkit
    just produces the canonical script — the same source the EPUB, PDF, and
    audiobook come from.
    """
    from .storyboard import plan_storyboard, slugify, write_storyboard

    t0 = time.time()
    cmd = "storyboard"
    book_dir = book_dir.resolve()
    config = _load_config(book_dir, cmd, output)

    missing = [c.file for c in config.chapters if not (book_dir / c.file).exists()]
    if missing:
        _die(
            cmd,
            output,
            code=ExitCode.PRECONDITION_FAILED,
            message=f"{len(missing)} chapter file(s) missing",
            hints=[f"missing: {m}" for m in missing],
        )

    bible_file = book_dir / "bible.yaml"
    bible = load_bible(bible_file) if bible_file.exists() else None

    plan = plan_storyboard(config, book_dir, bible=bible, max_panel_chars=max_panel_chars)
    target = (dest or (book_dir / f"{slugify(config.title)}-storyboard")).resolve()

    if dry_run:
        planned = [
            {"chapter": c.name, "title": c.title, "panels": len(c.panels)} for c in plan.chapters
        ]
        envelope = success_envelope(cmd, {}, start_time=t0, dry_run=True, planned_actions=planned)
        emit(envelope, output)
        raise typer.Exit(code=ExitCode.DRY_RUN)

    written = write_storyboard(plan, target, force=force)
    data = {
        "storyboard": str(target),
        "chapters": len(plan.chapters),
        "panels": plan.panel_count,
        "files_written": len(written),
    }
    if output == OutputFormat.text:
        print(f"Wrote storyboard to {target}")
        print(f"  chapters: {data['chapters']}")
        print(f"  panels:   {data['panels']}")
        print(f"  files:    {data['files_written']} written")
    else:
        emit(success_envelope(cmd, data, start_time=t0), output)


# ---------------------------------------------------------------------------
# Command group: write (AI-assisted)
# ---------------------------------------------------------------------------

write_app = typer.Typer(name="write", help="AI-assisted writing commands (outline, chapters).")
app.add_typer(write_app)

series_app = typer.Typer(name="series", help="Manage a collection of correlated books.")
app.add_typer(series_app)


@series_app.command("new")
def cmd_series_new(
    title: str = typer.Argument(..., help="Series title (used as the collection dir name)."),
    books: int = typer.Option(3, "--books", "-n", help="Number of books in the series."),
    chapters: int = typer.Option(1, "--chapters", "-c", help="Chapter stubs to create per book."),
    dest: Path = typer.Option(
        Path("."), "--dest", "-d", help="Parent directory for the new collection."
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", "-o", help="Output format (text|json)."
    ),
) -> None:
    """Scaffold a collection: a series.yaml plus linked book sub-directories."""
    t0 = time.time()
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "series"
    coll_dir = dest.resolve() / slug
    book_dirs = scaffold_series(title, coll_dir, num_books=books, chapters_per_book=chapters)

    data = {"series": title, "path": str(coll_dir), "books": book_dirs}
    if output == OutputFormat.text:
        print(f"Created series '{title}' at {coll_dir}")
        print("  series.yaml")
        for b in book_dirs:
            print(f"  {b}/ (book.yaml, bible.yaml, chapters/)")
    else:
        emit(success_envelope("series new", data, start_time=t0), output)


# ---------------------------------------------------------------------------
# Command group: check (continuity guard)
# ---------------------------------------------------------------------------

check_app = typer.Typer(name="check", help="Verify a book/series against its canon.")
app.add_typer(check_app)


def _llm_findings(book_dir: Path, bible: BibleConfig, writer_name: str, model: str | None) -> list:
    """Optional LLM continuity pass over each chapter with prose; best-effort."""
    from .continuity import Finding

    writer = get_writer(writer_name, model)
    out: list[Finding] = []
    for beat in sorted(bible.beats, key=lambda b: b.chapter):
        path = find_chapter_file(book_dir, beat.chapter)
        if not path:
            continue
        canon = bible_to_prompt_text(bible, upto_chapter=beat.chapter)
        system, user = build_continuity_prompts(
            canon, beat.chapter, path.read_text(encoding="utf-8")
        )
        try:
            _, block = split_prose_and_yaml(writer.complete(system, user))
            parsed = yaml.safe_load(block) if block else None
        except Exception:
            continue
        for item in (parsed or {}).get("findings", []) or []:
            out.append(
                Finding(
                    severity=str(item.get("severity", "warning")),
                    kind=f"llm:{item.get('kind', 'contradiction')}",
                    detail=str(item.get("detail", "")),
                    chapter=beat.chapter,
                )
            )
    return out


@check_app.command("continuity")
def cmd_check_continuity(
    book_dir: Path = typer.Option(
        Path("."), "--book-dir", "-b", help="Book directory (with bible.yaml)."
    ),
    collection: Path = typer.Option(
        None, "--collection", help="A collection dir (with series.yaml) to check whole."
    ),
    scan_prose: bool = typer.Option(
        False, "--scan-prose", help="Also scan chapter text (not just beats)."
    ),
    strict: bool = typer.Option(False, "--strict", help="Treat warnings as failures too."),
    llm: bool = typer.Option(False, "--llm", help="Add an LLM contradiction pass."),
    writer: str | None = typer.Option(
        None, "--writer", "-w", help="LLM backend for --llm. Default: $BOOKKIT_WRITER."
    ),
    model: str | None = typer.Option(None, "--model", "-m", help="Model name for --llm."),
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", "-o", help="Output format (text|json)."
    ),
) -> None:
    """Check a book (or a whole collection) for continuity violations against its canon."""
    t0 = time.time()
    cmd = "check continuity"
    writer_name = writer or default_writer_name()
    rows: list[dict] = []  # finding dicts, each optionally tagged with "book"

    def _run_book(bdir: Path, label: str | None) -> None:
        bible_file = bdir / "bible.yaml"
        if not bible_file.exists():
            _die(
                cmd,
                output,
                code=ExitCode.NOT_FOUND,
                message=f"bible.yaml not found in {bdir}",
                hint="Scaffold one with 'bookkit new' or 'bookkit write outline'.",
            )
        bible = load_bible(bible_file)
        book_yaml = bdir / "book.yaml"
        config = (
            BookConfig.model_validate(yaml.safe_load(book_yaml.read_text(encoding="utf-8")))
            if book_yaml.exists()
            else None
        )
        findings = check_book(bible, config, bdir, scan_prose=scan_prose)
        if llm:
            findings += _llm_findings(bdir, bible, writer_name, model)
        for f in findings:
            row = f.to_dict()
            if label:
                row["book"] = label
            rows.append(row)

    if collection is not None:
        coll = collection.resolve()
        series_file = coll / "series.yaml"
        if not series_file.exists():
            _die(
                cmd,
                output,
                code=ExitCode.NOT_FOUND,
                message=f"series.yaml not found in {coll}",
            )
        series = load_series(series_file)
        for f in check_series(series):
            rows.append(f.to_dict())
        for entry in series.books:
            _run_book(coll / entry.dir, entry.dir)
    else:
        _run_book(book_dir.resolve(), None)

    errors = sum(1 for r in rows if r["severity"] == "error")
    warnings = sum(1 for r in rows if r["severity"] == "warning")
    failed = errors > 0 or (strict and warnings > 0)

    if output == OutputFormat.text:
        for r in rows:
            where = f"{r['book']} " if r.get("book") else ""
            ch = f"ch{r['chapter']:>2}" if r.get("chapter") else "  -"
            print(f"  {where}{ch}  {r['severity'].upper():7} {r['kind']}: {r['detail']}")
        if not rows:
            print("No continuity issues found.")
        else:
            print(f"{len(rows)} issue(s): {errors} error(s), {warnings} warning(s)")
    else:
        data = {"findings": rows, "errors": errors, "warnings": warnings}
        emit(success_envelope(cmd, data, start_time=t0), output)

    if failed:
        raise typer.Exit(code=ExitCode.PRECONDITION_FAILED)


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
    series_context = ""
    sources_used = []

    bible_file = bible_path or (book_dir / "bible.yaml")
    bible = load_bible(bible_file) if bible_file.exists() else None

    # Series: if book.yaml links a series.yaml, fold in the shared cast and the
    # predecessor book's ending state so this book continues from where that ended.
    book_yaml = book_dir / "book.yaml"
    if book_yaml.exists():
        bconf = BookConfig.model_validate(yaml.safe_load(book_yaml.read_text(encoding="utf-8")))
        if bconf.series:
            series_path = book_dir / bconf.series
            if series_path.exists():
                series = load_series(series_path)
                series_context = series_context_text(series, book_dir.name)
                bible = merge_shared_characters(series, bible or BibleConfig())
                if series_context:
                    sources_used.append("series")

    if bible is not None:
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
        series_context=series_context,
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
                "name": "audiobook",
                "description": "Convert a book into a podcastkit project (script.json + "
                "episode.yaml per chapter); the bible.yaml cast becomes the voice cast. "
                "Render with podcastkit generate/assemble.",
                "idempotent": True,
                "options": [
                    {"name": "--book-dir", "short": "-b", "type": "path", "default": "."},
                    {"name": "--dest", "short": "-d", "type": "path", "default": None},
                    {
                        "name": "--backend",
                        "type": "enum[kokoro|chatterbox|openai|elevenlabs]",
                        "default": "kokoro",
                    },
                    {"name": "--voice", "type": "string", "default": "bm_george"},
                    {"name": "--narrator", "type": "string", "default": "NARRATOR"},
                    {"name": "--max-chars", "type": "integer", "default": 600},
                    {"name": "--cast", "type": "bool", "default": False},
                    {"name": "--force", "type": "bool", "default": False},
                    {"name": "--dry-run", "type": "bool", "default": False},
                    {
                        "name": "--output",
                        "short": "-o",
                        "type": "enum[text|json]",
                        "default": "text",
                    },
                ],
                "examples": [
                    {
                        "description": "Emit a podcastkit project for the book",
                        "invocation": "bookkit audiobook -b . --backend kokoro --voice bm_george",
                    },
                    {
                        "description": "Full-cast reading (attribute dialogue to characters)",
                        "invocation": "bookkit audiobook -b . --cast --backend openai",
                    },
                ],
            },
            {
                "name": "storyboard",
                "description": "Generate a storyboard (panel/shot script) from a book — the "
                "visual tier. One storyboard.json per chapter: panels with scene, attributed "
                "dialogue, characters present, and art notes from bible.yaml. Rendered by a "
                "comic or video tool.",
                "idempotent": True,
                "options": [
                    {"name": "--book-dir", "short": "-b", "type": "path", "default": "."},
                    {"name": "--dest", "short": "-d", "type": "path", "default": None},
                    {"name": "--max-panel-chars", "type": "integer", "default": 320},
                    {"name": "--force", "type": "bool", "default": False},
                    {"name": "--dry-run", "type": "bool", "default": False},
                    {
                        "name": "--output",
                        "short": "-o",
                        "type": "enum[text|json]",
                        "default": "text",
                    },
                ],
                "examples": [
                    {
                        "description": "Emit a storyboard for the book",
                        "invocation": "bookkit storyboard -b .",
                    }
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
            {
                "name": "series new",
                "description": "Scaffold a collection of correlated books: a series.yaml "
                "plus linked book sub-directories.",
                "idempotent": False,
                "arguments": [{"name": "title", "required": True, "description": "Series title."}],
                "options": [
                    {"name": "--books", "short": "-n", "type": "integer", "default": 3},
                    {"name": "--chapters", "short": "-c", "type": "integer", "default": 1},
                    {"name": "--dest", "short": "-d", "type": "path", "default": "."},
                    {
                        "name": "--output",
                        "short": "-o",
                        "type": "enum[text|json]",
                        "default": "text",
                    },
                ],
            },
            {
                "name": "check continuity",
                "description": "Check a book or collection for continuity violations "
                "against its canon (bible/series). Exit code 8 on errors.",
                "idempotent": True,
                "options": [
                    {"name": "--book-dir", "short": "-b", "type": "path", "default": "."},
                    {"name": "--collection", "type": "path", "default": None},
                    {"name": "--scan-prose", "type": "bool", "default": False},
                    {"name": "--strict", "type": "bool", "default": False},
                    {"name": "--llm", "type": "bool", "default": False},
                    {"name": "--writer", "short": "-w", "type": "string", "default": None},
                    {"name": "--model", "short": "-m", "type": "string", "default": None},
                    {
                        "name": "--output",
                        "short": "-o",
                        "type": "enum[text|json]",
                        "default": "text",
                    },
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
