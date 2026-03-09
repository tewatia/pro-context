"""Tool handler for search_page.

Validates input, fetches page content via the shared helper, compiles the
search matcher, runs the line scan, and returns matches with pagination.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog

from procontext.errors import ErrorCode, ProContextError
from procontext.models.tools import LineMatchOutput, SearchPageInput, SearchPageOutput
from procontext.outline import (
    build_compaction_note,
    compact_outline,
    format_outline,
    parse_outline_entries,
    strip_empty_fences,
    trim_outline_to_range,
)
from procontext.search import build_matcher, search_lines
from procontext.tools._shared import fetch_or_cached_page

if TYPE_CHECKING:
    from procontext.state import AppState


async def handle(
    url: str,
    query: str,
    state: AppState,
    *,
    mode: str = "literal",
    case_mode: str = "smart",
    whole_word: bool = False,
    offset: int = 1,
    max_results: int = 20,
) -> dict:
    """Handle a search_page tool call."""
    log = structlog.get_logger().bind(tool="search_page", url=url, query=query)
    log.info("handler_called")

    # Validate input
    try:
        validated = SearchPageInput(
            url=url,
            query=query,
            mode=mode,  # type: ignore[arg-type]
            case_mode=case_mode,  # type: ignore[arg-type]
            whole_word=whole_word,
            offset=offset,
            max_results=max_results,
        )
    except ValueError as exc:
        raise ProContextError(
            code=ErrorCode.INVALID_INPUT,
            message=str(exc),
            suggestion="Check url, query, mode, case_mode, offset, and max_results values.",
            recoverable=False,
        ) from exc

    # Fetch (or retrieve from cache) the page content
    result = await fetch_or_cached_page(validated.url, state)

    # Compile the search pattern
    try:
        matcher = build_matcher(
            validated.query,
            mode=validated.mode,
            case_mode=validated.case_mode,
            whole_word=validated.whole_word,
        )
    except re.error as exc:
        raise ProContextError(
            code=ErrorCode.INVALID_INPUT,
            message=f"Invalid regex pattern: {exc}",
            suggestion="Check your regex syntax or use mode='literal' for plain text search.",
            recoverable=False,
        ) from exc

    # Run the search
    search_result = search_lines(
        result.content,
        matcher,
        offset=validated.offset,
        max_results=validated.max_results,
    )

    total_lines = len(result.content.splitlines())

    # Build compacted outline trimmed to match range
    matches = [
        LineMatchOutput(line_number=m.line_number, content=m.content) for m in search_result.matches
    ]
    outline = _compact_search_outline(result.outline, matches)

    output = SearchPageOutput(
        url=result.url,
        query=validated.query,
        outline=outline,
        matches=matches,
        total_lines=total_lines,
        has_more=search_result.has_more,
        next_offset=search_result.next_offset,
        cached=result.cached,
        cached_at=result.cached_at,
    )
    return output.model_dump(mode="json")


def _compact_search_outline(raw_outline: str, matches: list[LineMatchOutput]) -> str:
    """Trim outline to match range and compact for search_page output."""
    if not matches:
        return ""

    entries = parse_outline_entries(raw_outline)
    entries = strip_empty_fences(entries)
    total_entries = len(entries)

    # Trim to match range
    first_line = matches[0].line_number
    last_line = matches[-1].line_number
    trimmed = trim_outline_to_range(entries, first_line, last_line)

    if len(trimmed) <= 50:
        return format_outline(trimmed)

    compacted = compact_outline(trimmed)
    if compacted is None:
        return (
            f"[Outline too large ({total_entries} entries). Use read_outline for paginated access.]"
        )

    note = build_compaction_note(compacted, total_entries, match_range=(first_line, last_line))
    return note + "\n" + format_outline(compacted)
