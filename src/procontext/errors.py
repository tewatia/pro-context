from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    LIBRARY_NOT_FOUND = "LIBRARY_NOT_FOUND"
    LLMS_TXT_NOT_FOUND = "LLMS_TXT_NOT_FOUND"
    LLMS_TXT_FETCH_FAILED = "LLMS_TXT_FETCH_FAILED"
    PAGE_NOT_FOUND = "PAGE_NOT_FOUND"
    PAGE_FETCH_FAILED = "PAGE_FETCH_FAILED"
    URL_NOT_ALLOWED = "URL_NOT_ALLOWED"
    INVALID_INPUT = "INVALID_INPUT"


class ProContextError(Exception):
    """Raised by tool handlers for all expected failure conditions.

    Caught by server.py and serialised into the MCP error response.
    Never catch this inside business logic — let it propagate to the
    MCP layer so the agent receives a structured error with a suggestion.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        suggestion: str,
        recoverable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.suggestion = suggestion
        self.recoverable = recoverable

    def to_dict(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "suggestion": self.suggestion,
                "recoverable": self.recoverable,
            }
        }
