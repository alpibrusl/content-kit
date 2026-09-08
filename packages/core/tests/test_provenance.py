"""A stamp that can be wrong is worse than no stamp, so these test the edges."""

from __future__ import annotations

import subprocess
from pathlib import Path

from content_kit_core.provenance import (
    SourceStamp,
    build_stamp,
    describe_source,
    describe_tool,
)


def _repo(tmp_path: Path) -> Path:
    d = tmp_path / "repo"
    d.mkdir()
    for args in (
        ["init", "-q"],
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "T"],
    ):
        subprocess.run(["git", *args], cwd=d, check=True, capture_output=True)
    (d / "a.md").write_text("one\n")
    subprocess.run(["git", "add", "-A"], cwd=d, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "first"], cwd=d, check=True, capture_output=True)
    return d


def test_a_directory_outside_git_claims_no_commit(tmp_path: Path) -> None:
    """A build from a tarball is a legitimate build. It just cannot claim a
    commit, and must say so rather than invent one."""
    stamp = describe_source(tmp_path)
    assert stamp.commit == "unknown"
    assert str(stamp) == "no recorded commit"


def test_a_clean_checkout_reports_its_commit(tmp_path: Path) -> None:
    stamp = describe_source(_repo(tmp_path))
    assert len(stamp.commit) >= 7
    assert stamp.dirty is False
    assert "dirty" not in str(stamp)


def test_an_uncommitted_change_anywhere_marks_the_build_dirty(tmp_path: Path) -> None:
    """Repository-wide on purpose. A stylesheet edited outside the book
    directory still changes the rendered PDF, and a stamp reporting "clean"
    because the change sat elsewhere would be worse than no stamp."""
    d = _repo(tmp_path)
    (d / "elsewhere.css").write_text("body { color: red }\n")
    assert describe_source(d).dirty is True
    assert str(describe_source(d)).endswith("-dirty")


def test_a_tag_replaces_the_hash_only_when_it_is_exact(tmp_path: Path) -> None:
    """`describe --exact-match`, not the nearest tag: "v1.0-14-gabc" reads like
    a version and is not one."""
    d = _repo(tmp_path)
    subprocess.run(["git", "tag", "v1.0"], cwd=d, check=True, capture_output=True)
    assert str(describe_source(d)) == "v1.0"

    (d / "b.md").write_text("two\n")
    subprocess.run(["git", "add", "-A"], cwd=d, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "second"], cwd=d, check=True, capture_output=True)
    moved = describe_source(d)
    assert moved.tag == ""
    assert str(moved) == moved.commit


def test_an_uninstalled_tool_degrades_to_its_name() -> None:
    assert str(describe_tool("a-package-nobody-installed")) == "a-package-nobody-installed"


def test_the_stamp_names_the_source_and_every_tool(tmp_path: Path) -> None:
    line = build_stamp(_repo(tmp_path), ["content-kit-core"])
    assert line.startswith("source ")
    assert "content-kit-core" in line


def test_a_file_path_is_described_by_its_directory(tmp_path: Path) -> None:
    d = _repo(tmp_path)
    assert describe_source(d / "a.md").commit == describe_source(d).commit


def test_str_of_a_bare_stamp_is_not_a_traceback() -> None:
    assert str(SourceStamp()) == "no recorded commit"
