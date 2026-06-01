from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from bookkit._manuscript import load_chapters
from bookkit.config import BookConfig

epub = pytest.importorskip("ebooklib.epub", reason="ebooklib not installed")


def _epub_text(path: Path) -> str:
    z = zipfile.ZipFile(path)
    return " ".join(
        z.read(n).decode("utf-8", "ignore") for n in z.namelist() if n.endswith(".xhtml")
    )


def test_epub_includes_front_matter_and_license(tmp_path: Path) -> None:
    from bookkit.renderers.epub import EpubRenderer

    (tmp_path / "01.md").write_text("# One\n\nBody.\n", encoding="utf-8")
    cfg = BookConfig.model_validate(
        {
            "title": "Mi Libro",
            "author": {"name": "Sienna Frost"},
            "language": "es",
            "chapters": [{"file": "01.md"}],
            "front_matter": ["title_page", "copyright", "toc"],
            "copyright": {
                "year": "2026",
                "license": "CC BY-NC-ND 4.0",
                "notice": ["Hecho con asistencia de IA."],
            },
        }
    )
    chapters = load_chapters(cfg, tmp_path)
    dest = tmp_path / "out.epub"
    EpubRenderer().render(cfg, chapters, tmp_path, dest)

    text = _epub_text(dest)
    assert "Sienna Frost" in text  # title page author
    assert "CC BY-NC-ND 4.0" in text  # license label
    assert "Hecho con asistencia de IA." in text  # notice paragraph
    assert "Body." in text  # chapter body still present
