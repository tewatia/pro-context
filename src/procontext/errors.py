from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    PAGE_NOT_FOUND = "PAGE_NOT_FOUND"
    PAGE_FETCH_FAILED = "PAGE_FETCH_FAILED"
    TOO_MANY_REDIRECTS = "TOO_MANY_REDIRECTS"
    URL_NOT_ALLOWED = "URL_NOT_ALLOWED"
    INVALID_INPUT = "INVALID_INPUT"


class ProContextError(Exception):
    """Raised by tool handlers for all expected failure conditions.

    Propagates to FastMCP which converts it to an isError=True tool result.
    Never catch this inside business logic.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        suggestion: str,
        recoverable: bool = False,
    ) -> None:
        super().__init__(f"{code}: {message}. {suggestion}")
        self.code = code
        self.message = message
        self.suggestion = suggestion
        self.recoverable = recoverable
