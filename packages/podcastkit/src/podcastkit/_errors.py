"""podcastkit error types — the shared hierarchy from content_kit_core.

``PodcastKitError`` is kept as an alias of the platform-wide ``ContentKitError``
so existing ``raise``/``except PodcastKitError`` sites are unchanged.
"""

from __future__ import annotations

from content_kit_core._errors import (
    ContentKitError as PodcastKitError,
)
from content_kit_core._errors import (
    InvalidArgsError,
    NotFoundError,
    PreconditionError,
    UpstreamError,
)

__all__ = [
    "PodcastKitError",
    "InvalidArgsError",
    "NotFoundError",
    "PreconditionError",
    "UpstreamError",
]
