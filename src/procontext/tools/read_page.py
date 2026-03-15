"""Tool handler for read_page.

Validates input, delegates fetching to the shared helper, applies outline
compaction, and applies line windowing to build the output dict.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from procontext.errors import ErrorCode, ProContextError
from procontext.models.tools import ReadPageInput, ReadPageOutput
from procontext.outline import (
    build_compaction_note,
    compact_outline,
    format_outline,
    parse_outline_entries,
    strip_empty_fences,
)
from procontext.tools._shared import fetch_or_cached_page

if TYPE_CHECKING:
    from datetime import datetime

    from procontext.state import AppState


async def handle(
    url: str,
    offset: int,
    limit: int,
    state: AppState,
) -> dict:
    """Handle a read_page tool call."""
    log = structlog.get_logger().bind(tool="read_page", url=url)
    log.info("handler_called")

    # Validate input
    try:
        validated = ReadPageInput(url=url, offset=offset, limit=limit)
    except ValueError as exc:
        raise ProContextError(
            code=ErrorCode.INVALID_INPUT,
            message=str(exc),
            suggestion="Provide a valid URL (http/https, max 2048 chars), offset >= 1, limit >= 1.",
            recoverable=False,
        ) from exc

    result = await fetch_or_cached_page(validated.url, state)

    # Compact the outline
    compacted_outline = _compact_page_outline(result.outline)

    return _build_output(
        url=result.url,
        content=result.content,
        outline=compacted_outline,
        offset=validated.offset,
        limit=validated.limit,
        content_hash=result.content_hash,
        cached=result.cached,
        cached_at=result.cached_at,
        stale=result.stale,
    )


def _compact_page_outline(raw_outline: str) -> str:
    """Parse, strip empty fences, and compact an outline for read_page output."""
    entries = parse_outline_entries(raw_outline)
    entries = strip_empty_fences(entries)
    total_entries = len(entries)

    if total_entries <= 50:
        return format_outline(entries)

    compacted = compact_outline(entries)
    if compacted is None:
        return (
            f"[Outline too large ({total_entries} entries). Use read_outline for paginated access.]"
        )

    note = build_compaction_note(compacted, total_entries)
    return note + "\n" + format_outline(compacted)


def _build_output(
    *,
    url: str,
    content: str,
    outline: str,
    offset: int,
    limit: int,
    content_hash: str,
    cached: bool,
    cached_at: datetime | None,
    stale: bool,
) -> dict:
    """Apply line windowing and build the output dict."""
    all_lines = content.splitlines()
    total_lines = len(all_lines)

    windowed = all_lines[offset - 1 : offset - 1 + limit]
    windowed_content = "\n".join(windowed)

    end = offset - 1 + limit
    has_more = end < total_lines
    next_offset = end + 1 if has_more else None

    output = ReadPageOutput(
        url=url,
        outline=outline,
        total_lines=total_lines,
        offset=offset,
        limit=limit,
        content=windowed_content,
        has_more=has_more,
        next_offset=next_offset,
        content_hash=content_hash,
        cached=cached,
        cached_at=cached_at,
        stale=stale,
    )
    return output.model_dump(mode="json")
