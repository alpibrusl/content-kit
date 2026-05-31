from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from bookkit.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip()


def test_introspect_is_json() -> None:
    result = runner.invoke(app, ["introspect"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    names = {c["name"] for c in payload["data"]["commands"]}
    assert {"new", "build"} <= names


def test_new_scaffolds_book(tmp_path: Path) -> None:
    result = runner.invoke(app, ["new", "My Book", "-n", "3", "-d", str(tmp_path)])
    assert result.exit_code == 0
    book_dir = tmp_path / "my-book"
    assert (book_dir / "book.yaml").exists()
    assert (book_dir / "chapters" / "01-chapter.md").exists()
    assert (book_dir / "chapters" / "03-chapter.md").exists()


def test_build_missing_config_errors(tmp_path: Path) -> None:
    result = runner.invoke(app, ["build", "-b", str(tmp_path), "-o", "json"])
    assert result.exit_code == 3  # NOT_FOUND
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "NOT_FOUND"


def test_build_invalid_format_errors(tmp_book: Path) -> None:
    result = runner.invoke(app, ["build", "-b", str(tmp_book), "-f", "mobi", "-o", "json"])
    assert result.exit_code == 2  # INVALID_ARGS
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "INVALID_ARGS"


def test_build_dry_run(tmp_book: Path) -> None:
    result = runner.invoke(
        app, ["build", "-b", str(tmp_book), "-f", "html", "--dry-run", "-o", "json"]
    )
    assert result.exit_code == 9  # DRY_RUN
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["planned_actions"][0]["chapters"] == 2


def test_build_html_end_to_end(tmp_book: Path) -> None:
    result = runner.invoke(app, ["build", "-b", str(tmp_book), "-f", "html", "-o", "json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    out = Path(payload["data"]["output"])
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    # front matter + both chapters present
    assert "Test Book" in html
    assert "Introduction" in html
    assert "First Principles" in html
    assert "About the Author" in html  # back matter
    assert payload["data"]["chapters"] == 2
    assert payload["data"]["words"] > 0


def test_build_missing_chapter_file(tmp_book: Path) -> None:
    (tmp_book / "chapters" / "02-method.md").unlink()
    result = runner.invoke(app, ["build", "-b", str(tmp_book), "-f", "html", "-o", "json"])
    assert result.exit_code == 8  # PRECONDITION_FAILED
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "PRECONDITION_FAILED"
