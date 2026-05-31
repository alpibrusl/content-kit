from __future__ import annotations

from pathlib import Path

import yaml

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_CHAPTER_TEMPLATE = _TEMPLATES_DIR / "chapters" / "chapter.md"


def _book_config_dict(title: str, chapter_files: list[str]) -> dict:
    """The default book.yaml contents for a freshly scaffolded book."""
    return {
        "title": title,
        "subtitle": "",
        "author": {"name": "", "bio": ""},
        "language": "en",
        "output": "book.epub",
        "cover": "",
        "isbn": "",
        "theme": {"base_font": "serif", "page_size": "6x9", "font_size_pt": 11.0},
        "chapters": [{"file": f, "title": ""} for f in chapter_files],
        "front_matter": ["title_page", "toc"],
        "back_matter": [],
    }


def scaffold_book(title: str, dest: Path, num_chapters: int = 1) -> list[str]:
    """Create a new book directory at dest.

    Writes one ``book.yaml`` referencing ``num_chapters`` Markdown stubs under
    ``chapters/``. Existing files are never clobbered, so re-running over a book in
    progress is safe. Returns the list of chapter file paths (relative to dest).
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
                _book_config_dict(title, chapter_files),
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
