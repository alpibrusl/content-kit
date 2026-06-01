from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    GENERAL_ERROR = 1
    INVALID_ARGS = 2
    NOT_FOUND = 3
    PERMISSION_DENIED = 4
    CONFLICT = 5
    TIMEOUT = 6
    UPSTREAM_ERROR = 7
    PRECONDITION_FAILED = 8
    DRY_RUN = 9
