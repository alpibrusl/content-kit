"""Output format handling and JSON envelopes — see content_kit_core._output.

Re-exported from the shared core so every tool in the platform speaks the same
envelope/exit-code protocol. Kept as a module so existing ``from ._output import
...`` sites are unchanged.
"""

from __future__ import annotations

from content_kit_core._output import (
    VERSION,
    OutputFormat,
    emit,
    emit_progress,
    error_envelope,
    success_envelope,
)

__all__ = [
    "VERSION",
    "OutputFormat",
    "emit",
    "emit_progress",
    "error_envelope",
    "success_envelope",
]
