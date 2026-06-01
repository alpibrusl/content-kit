from __future__ import annotations

from ._exit_codes import ExitCode


class ContentKitError(Exception):
    """Base error for content-kit commands. Always includes an actionable hint.

    Each tool re-exports this under its own historical name (``BookKitError``,
    ``PodcastKitError``) so existing ``except`` sites keep working unchanged.
    """

    def __init__(
        self,
        message: str,
        *,
        code: ExitCode = ExitCode.GENERAL_ERROR,
        hint: str | None = None,
        hints: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint
        self.hints = hints


class InvalidArgsError(ContentKitError):
    def __init__(
        self, message: str, *, hint: str | None = None, hints: list[str] | None = None
    ) -> None:
        super().__init__(message, code=ExitCode.INVALID_ARGS, hint=hint, hints=hints)


class NotFoundError(ContentKitError):
    def __init__(
        self, message: str, *, hint: str | None = None, hints: list[str] | None = None
    ) -> None:
        super().__init__(message, code=ExitCode.NOT_FOUND, hint=hint, hints=hints)


class PreconditionError(ContentKitError):
    def __init__(
        self, message: str, *, hint: str | None = None, hints: list[str] | None = None
    ) -> None:
        super().__init__(message, code=ExitCode.PRECONDITION_FAILED, hint=hint, hints=hints)


class UpstreamError(ContentKitError):
    def __init__(
        self, message: str, *, hint: str | None = None, hints: list[str] | None = None
    ) -> None:
        super().__init__(message, code=ExitCode.UPSTREAM_ERROR, hint=hint, hints=hints)
