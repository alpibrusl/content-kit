from __future__ import annotations

from pathlib import Path

import yaml

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_CHAPTER_TEMPLATE = _TEMPLATES_DIR / "chapters" / "chapter.md"


def _book_config_dict(title: str, chapter_files: list[str], series: str | None = None) -> dict:
    """The default book.yaml contents for a freshly scaffolded book."""
    config: dict = {
        "title": title,
        "subtitle": "",
        "author": {"name": "", "bio": ""},
        "language": "en",
        "output": "book.epub",
        "cover": "",
        "isbn": "",
    }
    if series:
        config["series"] = series
    config.update(
        {
            "theme": {"base_font": "serif", "page_size": "6x9", "font_size_pt": 11.0},
            "chapters": [{"file": f, "title": ""} for f in chapter_files],
            "front_matter": ["title_page", "toc"],
            "back_matter": [],
        }
    )
    return config


def scaffold_book(
    title: str, dest: Path, num_chapters: int = 1, *, series: str | None = None
) -> list[str]:
    """Create a new book directory at dest.

    Writes one ``book.yaml`` referencing ``num_chapters`` Markdown stubs under
    ``chapters/``. Existing files are never clobbered, so re-running over a book in
    progress is safe. When ``series`` is given it is recorded in book.yaml so the
    book is generated against a shared series bible. Returns the chapter file paths.
    """
    dest.mkdir(parents=True, exist_ok=True)
    chapters_dir = dest / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)

    template = _CHAPTER_TEMPLATE.read_text(encoding="utf-8")
    chapter_files: list[str] = []
    for n in range(1, num_chapters + 1):
        rel = f"chapters/{n:02d}-chapter.md"
        chapter_files.append(rel)
        chapter_path = dest / rel
        if not chapter_path.exists():
            chapter_path.write_text(template.replace("{{NUMBER}}", str(n)), encoding="utf-8")

    book_yaml = dest / "book.yaml"
    if not book_yaml.exists():
        book_yaml.write_text(
            yaml.dump(
                _book_config_dict(title, chapter_files, series=series),
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    bible_yaml = dest / "bible.yaml"
    if not bible_yaml.exists():
        bible_yaml.write_text(
            yaml.dump(
                _bible_stub_dict(title, num_chapters),
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
    return chapter_files


def _bible_stub_dict(title: str, num_chapters: int) -> dict:
    """A starter bible.yaml (canon) with one empty beat per chapter to fill in."""
    return {
        "title": title,
        "logline": "",
        "themes": [],
        "characters": [
            {
                "name": "",
                "role": "",
                "description": "",
                "voice": "",
                "arc": "",
                "status": "alive",
                "first_appears": 1,
            }
        ],
        "beats": [
            {"chapter": n, "summary": "", "advances": [], "state_changes": []}
            for n in range(1, num_chapters + 1)
        ],
    }


def scaffold_series(
    title: str, dest: Path, num_books: int = 3, chapters_per_book: int = 1
) -> list[str]:
    """Create a collection directory: a series.yaml plus N book sub-directories.

    Each book is scaffolded with ``scaffold_book`` and linked back to the shared
    ``series.yaml`` so its chapters are generated against the series bible. Returns
    the list of book directory names. Existing files are never clobbered.
    """
    dest.mkdir(parents=True, exist_ok=True)
    book_dirs: list[str] = []
    prev: str | None = None
    book_entries: list[dict] = []
    for i in range(1, num_books + 1):
        book_dir = f"book-{i:02d}"
        book_title = f"{title} — Book {i}"
        scaffold_book(book_title, dest / book_dir, chapters_per_book, series="../series.yaml")
        book_entries.append(
            {
                "dir": book_dir,
                "title": book_title,
                "role": "",
                "opens_from": prev,
                "ends_with_state": [],
            }
        )
        book_dirs.append(book_dir)
        prev = book_dir

    series_yaml = dest / "series.yaml"
    if not series_yaml.exists():
        series_yaml.write_text(
            yaml.dump(
                {
                    "series": title,
                    "arc": "",
                    "shared_characters": [
                        {"name": "", "role": "", "description": "", "voice": "", "status": "alive"}
                    ],
                    "books": book_entries,
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
    return book_dirs
