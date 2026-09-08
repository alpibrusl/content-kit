"""What a rendered artifact needs in order to be reproducible.

*Prompt to Production* opens by insisting that an artifact is derived rather
than authored, and that losing one should not matter because you can rebuild an
equivalent from the source and the recorded build inputs. An artifact that does
not record those inputs cannot make that claim, so the books and the cohort
documents stamp them.

Two inputs, and the second is the one people forget. The manuscript's commit is
obvious. The toolchain's matters just as much here, because every book installs
bookkit and cohortkit from ``@main`` rather than from a release: "bookkit 0.1.0"
names a moving target, and two builds a week apart from the same commit can
differ. So the stamp carries the toolchain's commit where pip recorded one.

Everything degrades rather than raising. A build from a tarball with no git
history is a legitimate build; it simply cannot claim a commit, and the stamp
says so instead of inventing one.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

__all__ = ["SourceStamp", "ToolStamp", "describe_source", "describe_tool", "build_stamp"]

_UNKNOWN = "unknown"


@dataclass(frozen=True)
class SourceStamp:
    """Where the manuscript stood when the artifact was built."""

    commit: str = _UNKNOWN
    """Short commit hash, or "unknown" outside a git checkout."""

    dirty: bool = False
    """Whether anything in the repository was uncommitted.

    Repository-wide on purpose, not scoped to the book directory. A stylesheet
    edited two directories up changes the rendered PDF, and a stamp that
    reported "clean" because the change sat outside the book would be worse
    than no stamp at all.
    """

    tag: str = ""
    """The exact tag on this commit, when there is one. Empty otherwise --
    `git describe --exact-match`, not the nearest tag, because "v1.0-14-gabc"
    reads like a version and is not one."""

    def __str__(self) -> str:
        if self.commit == _UNKNOWN:
            return "no recorded commit"
        head = self.tag or self.commit
        return f"{head}-dirty" if self.dirty else head


@dataclass(frozen=True)
class ToolStamp:
    """Which build of the toolchain produced the artifact."""

    name: str
    version: str = _UNKNOWN
    commit: str = ""
    """The commit pip recorded for a VCS install, or the checkout's HEAD for an
    editable one. Empty when neither applies -- a wheel from an index."""

    def __str__(self) -> str:
        if self.version == _UNKNOWN:
            return self.name
        if self.commit:
            return f"{self.name} {self.version} ({self.commit})"
        return f"{self.name} {self.version}"


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def describe_source(path: Path | str) -> SourceStamp:
    """Describe the git checkout ``path`` sits in, if it sits in one."""
    d = Path(path).resolve()
    if not d.is_dir():
        d = d.parent
    commit = _git(["rev-parse", "--short", "HEAD"], d)
    if commit is None:
        return SourceStamp()
    status = _git(["status", "--porcelain"], d)
    tag = _git(["describe", "--tags", "--exact-match"], d) or ""
    return SourceStamp(commit=commit, dirty=bool(status), tag=tag)


def describe_tool(name: str) -> ToolStamp:
    """Describe an installed distribution, including where pip got it from."""
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return ToolStamp(name=name)

    version = dist.version
    commit = ""
    try:
        raw = dist.read_text("direct_url.json")
    except (OSError, ValueError):
        raw = None
    if raw:
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            info = {}
        vcs = info.get("vcs_info") or {}
        commit = (vcs.get("commit_id") or "")[:7]
        # An editable install has no commit_id: it points at a working copy,
        # so ask that working copy directly. This is the case while developing,
        # and it is exactly when a stamp is most likely to be misleading.
        if not commit and (info.get("dir_info") or {}).get("editable"):
            url = info.get("url", "")
            if url.startswith("file://"):
                stamp = describe_source(Path(url[7:]))
                commit = str(stamp) if stamp.commit != _UNKNOWN else ""
    return ToolStamp(name=name, version=version, commit=commit)


def build_stamp(source: Path | str, tools: list[str]) -> str:
    """One line naming everything needed to rebuild this artifact."""
    parts = [f"source {describe_source(source)}"]
    parts += [str(describe_tool(t)) for t in tools]
    return " · ".join(parts)
