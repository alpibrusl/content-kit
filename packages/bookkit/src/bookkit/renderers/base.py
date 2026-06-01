from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from .._manuscript import Chapter
from ..config import BookConfig


class Renderer(ABC):
    """A renderer turns parsed chapters into a single book artifact on disk.

    Renderers are to bookkit what TTS backends are to podcastkit: pluggable,
    optionally-installed implementations selected at build time.
    """

    #: filename extension produced by this renderer, e.g. "epub"
    extension: str

    @abstractmethod
    def render(
        self,
        config: BookConfig,
        chapters: list[Chapter],
        book_dir: Path,
        dest: Path,
    ) -> None:
        """Render the book to dest. Implementations create dest's parent if needed."""
