"""bookkit error types — the shared hierarchy from content_kit_core.

``BookKitError`` is kept as an alias of the platform-wide ``ContentKitError`` so
existing ``raise``/``except BookKitError`` sites are unchanged.
"""

from __future__ import annotations

from content_kit_core._errors import (
    ContentKitError as BookKitError,
)
from content_kit_core._errors import (
    InvalidArgsError,
    NotFoundError,
    PreconditionError,
    UpstreamError,
)

__all__ = [
    "BookKitError",
    "InvalidArgsError",
    "NotFoundError",
    "PreconditionError",
    "UpstreamError",
]
