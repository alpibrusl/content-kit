from __future__ import annotations

from .base import Renderer

VALID_FORMATS = ("epub", "pdf", "html")


def get_renderer(name: str) -> Renderer:
    """Return a Renderer instance for the given output format.

    Imports are deferred so optional dependencies (ebooklib, weasyprint) are only
    required when their format is actually requested.
    """
    if name == "html":
        from .html import HtmlRenderer

        return HtmlRenderer()
    if name == "epub":
        from .epub import EpubRenderer

        return EpubRenderer()
    if name == "pdf":
        from .pdf import PdfRenderer

        return PdfRenderer()
    raise ValueError(f"Unknown format: {name!r}. Valid choices are: {', '.join(VALID_FORMATS)}.")


__all__ = ["Renderer", "get_renderer", "VALID_FORMATS"]
