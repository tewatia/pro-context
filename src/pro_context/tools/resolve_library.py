"""Tool handler for resolve-library.

Receives AppState, delegates to the resolver module, and returns
a structured dict. No MCP or FastMCP imports — server.py handles
the MCP wiring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from pro_context.errors import ErrorCode, ProContextError
from pro_context.models.tools import ResolveLibraryInput, ResolveLibraryOutput
from pro_context.resolver import resolve_library

if TYPE_CHECKING:
    from pro_context.state import AppState


async def handle(query: str, state: AppState) -> dict:
    """Handle a resolve-library tool call."""
    log = structlog.get_logger().bind(tool="resolve_library", query=query)
    log.info("handler_called")

    # Validate input
    try:
        validated = ResolveLibraryInput(query=query)
    except ValueError as exc:
        raise ProContextError(
            code=ErrorCode.INVALID_INPUT,
            message=str(exc),
            suggestion="Provide a non-empty library name, package name, or alias (max 500 chars).",
            recoverable=False,
        ) from exc

    matches = resolve_library(validated.query, state.indexes)
    log.info("resolve_complete", match_count=len(matches))

    output = ResolveLibraryOutput(matches=matches)
    return output.model_dump(mode="json")
