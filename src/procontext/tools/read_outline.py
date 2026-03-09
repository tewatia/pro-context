"""Tool handler for read_outline.

Validates input, delegates fetching to the shared helper, strips empty fences,
paginates outline entries by entry index, and returns the formatted result.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from procontext.errors import ErrorCode, ProContextError
from procontext.models.tools import ReadOutlineInput, ReadOutlineOutput
from procontext.outline import format_outline, parse_outline_entries, strip_empty_fences
from procontext.tools._shared import fetch_or_cached_page

if TYPE_CHECKING:
    from procontext.state import AppState


async def handle(
    url: str,
    offset: int,
    limit: int,
    state: AppState,
) -> dict:
    """Handle a read_outline tool call."""
    log = structlog.get_logger().bind(tool="read_outline", url=url)
    log.info("handler_called")

    # Validate input
    try:
        validated = ReadOutlineInput(url=url, offset=offset, limit=limit)
    except ValueError as exc:
        raise ProContextError(
            code=ErrorCode.INVALID_INPUT,
            message=str(exc),
            suggestion=(
                "Provide a valid URL (http/https, max 2048 chars), "
                "offset >= 1, limit between 1 and 500."
            ),
            recoverable=False,
        ) from exc

    result = await fetch_or_cached_page(validated.url, state)

    # Parse and strip empty fences (no compaction for read_outline)
    entries = parse_outline_entries(result.outline)
    entries = strip_empty_fences(entries)
    total_entries = len(entries)

    # Paginate by entry index (1-based offset)
    start = validated.offset - 1
    end = start + validated.limit
    page = entries[start:end]

    has_more = end < total_entries
    next_offset = end + 1 if has_more else None

    output = ReadOutlineOutput(
        url=result.url,
        outline=format_outline(page),
        total_entries=total_entries,
        has_more=has_more,
        next_offset=next_offset,
        cached=result.cached,
        cached_at=result.cached_at,
        stale=result.stale,
    )
    return output.model_dump(mode="json")
