"""bookkit's LLM writers — the platform-wide factory from content_kit_core.

The ``Writer`` backends and ``get_writer`` factory live in the shared core so a
provider added once is available to every tool. Kept as a module so existing
``from .writers import get_writer, default_writer_name`` sites are unchanged.
"""

from __future__ import annotations

from content_kit_core.writers import Writer, default_writer_name, get_writer

__all__ = ["Writer", "get_writer", "default_writer_name"]
