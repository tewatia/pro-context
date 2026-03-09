"""MCP tool registrations.

Defines the FastMCP instance and registers the ProContext tools.
Startup, logging setup, and lifespan management live in their own modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

import structlog
from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

import procontext.tools.read_outline as t_read_outline
import procontext.tools.read_page as t_read_page
import procontext.tools.resolve_library as t_resolve
import procontext.tools.search_page as t_search_page
from procontext import __version__
from procontext.errors import ProContextError
from procontext.mcp.lifespan import lifespan
from procontext.models.tools import (
    ReadOutlineOutput,
    ReadPageOutput,
    ResolveLibraryOutput,
    SearchPageOutput,
)

if TYPE_CHECKING:
    from procontext.state import AppState

log = structlog.get_logger()

mcp = FastMCP("procontext", lifespan=lifespan)
# FastMCP doesn't expose a version kwarg — set it on the underlying Server
# so the MCP initialize handshake reports our version, not the SDK's.
mcp._mcp_server.version = __version__  # pyright: ignore[reportPrivateUsage]


@mcp.tool()
async def resolve_library(
    query: Annotated[
        str,
        Field(
            description="Library name, package specifier (e.g. 'langchain-community'), or alias."
        ),
    ],
    ctx: Context,
) -> ResolveLibraryOutput:
    """Resolve a library name to its documentation source.

    Accepts a library name, package specifier (e.g. 'langchain-community'), or alias.
    Matched in priority order: exact PyPI/npm package names, canonical library IDs,
    registered aliases, then fuzzy name matching.

    Always call this first to identify a library and obtain its documentation URLs.
    Then pass the index_url to read_page to get the documentation index.

    Response:
      matches        — ranked list of results, sorted by relevance descending
      Each match contains:
        library_id   — canonical library identifier
        name         — human-readable library name
        index_url    — URL of the documentation index (pass to read_page)
        readme_url   — README URL (may be null)
        languages    — programming languages the library supports
        matched_via  — "package_name" | "library_id" | "alias" | "fuzzy"
        relevance    — confidence score 0.0 (low) to 1.0 (high)

    An empty matches list means the library is not in the registry.
    """
    state: AppState = ctx.request_context.lifespan_context
    try:
        return ResolveLibraryOutput.model_validate(await t_resolve.handle(query, state))
    except ProContextError as exc:
        log.warning("tool_error", tool="resolve_library", code=exc.code, message=exc.message)
        raise
    except Exception:
        log.error("tool_unexpected_error", tool="resolve_library", exc_info=True)
        raise


@mcp.tool()
async def read_page(
    url: Annotated[
        str,
        Field(description="Documentation page URL."),
    ],
    ctx: Context,
    offset: Annotated[
        int,
        Field(description="1-based line number to start reading from.", ge=1),
    ] = 1,
    limit: Annotated[
        int,
        Field(description="Maximum number of content lines to return.", ge=1),
    ] = 500,
) -> ReadPageOutput:
    """Fetch the outline and content of a documentation page.

    Accepts any documentation URL — typically the index_url from
    resolve_library or a link found within a previously fetched page.

    Navigation: Use outline line numbers to identify the section you need,
    then call again with offset=<line>. For pages with very large outlines,
    use read_outline for paginated browsing.

    Response:
      url          — the URL of the fetched page
      outline      — compacted structural outline (target ≤50 entries) with
                     1-based line numbers, e.g. "1:# Title\\n42:## Usage"
      total_lines  — total line count of the full page
      offset       — 1-based line number where the content window starts
      limit        — maximum lines in the content window
      content      — the content window
      has_more     — true if more content exists beyond the current window
      next_offset  — line number to pass as offset to continue; null if no more
      cached       — true if served from cache
      cached_at    — ISO timestamp of last fetch; null for fresh network responses
      stale        — true if cache entry is expired; background refresh in progress

    If has_more is true, call again with offset=next_offset to continue
    reading. Repeated calls on the same URL are served from cache (sub-100ms).
    """
    state: AppState = ctx.request_context.lifespan_context
    try:
        return ReadPageOutput.model_validate(await t_read_page.handle(url, offset, limit, state))
    except ProContextError as exc:
        log.warning("tool_error", tool="read_page", code=exc.code, message=exc.message)
        raise
    except Exception:
        log.error("tool_unexpected_error", tool="read_page", exc_info=True)
        raise


@mcp.tool()
async def read_outline(
    url: Annotated[
        str,
        Field(description="Documentation page URL."),
    ],
    ctx: Context,
    offset: Annotated[
        int,
        Field(description="1-based outline entry index to start from.", ge=1),
    ] = 1,
    limit: Annotated[
        int,
        Field(description="Maximum number of outline entries to return.", ge=1, le=500),
    ] = 200,
) -> ReadOutlineOutput:
    """Browse the full outline of a documentation page with pagination.

    Returns paginated outline entries (headings and fence markers with line
    numbers). Use this when read_page reports that the outline is too large
    for inline display, or when you need to browse the complete page structure.

    Outline entries have empty fence pairs pre-stripped. Pagination uses
    entry indices (not line numbers) — pass next_offset to continue browsing.

    Response:
      url           — the URL of the fetched page
      outline       — paginated outline entries, e.g. "1:# Title\\n42:## Usage"
      total_entries — total outline entries (after stripping empty fences)
      has_more      — true if more entries exist beyond the current window
      next_offset   — entry index to pass as offset to continue; null if no more
      cached        — true if served from cache
      cached_at     — ISO timestamp of last fetch; null for fresh network responses
      stale         — true if cache entry is expired; background refresh in progress
    """
    state: AppState = ctx.request_context.lifespan_context
    try:
        return ReadOutlineOutput.model_validate(
            await t_read_outline.handle(url, offset, limit, state)
        )
    except ProContextError as exc:
        log.warning("tool_error", tool="read_outline", code=exc.code, message=exc.message)
        raise
    except Exception:
        log.error("tool_unexpected_error", tool="read_outline", exc_info=True)
        raise


@mcp.tool()
async def search_page(
    url: Annotated[
        str,
        Field(description="URL of the page to search."),
    ],
    query: Annotated[
        str,
        Field(description="Search term or regex pattern."),
    ],
    ctx: Context,
    mode: Annotated[
        Literal["literal", "regex"],
        Field(
            description=(
                "literal: exact substring match. regex: treat query as a regular expression."
            )
        ),
    ] = "literal",
    case_mode: Annotated[
        Literal["smart", "insensitive", "sensitive"],
        Field(
            description=(
                "smart: lowercase query → case-insensitive; mixed/uppercase → case-sensitive. "
                "insensitive: always case-insensitive. "
                "sensitive: always case-sensitive."
            )
        ),
    ] = "smart",
    whole_word: Annotated[
        bool,
        Field(description="When true, match only at word boundaries."),
    ] = False,
    offset: Annotated[
        int,
        Field(description="1-based line number to start searching from.", ge=1),
    ] = 1,
    max_results: Annotated[
        int,
        Field(description="Maximum number of matching lines to return.", ge=1),
    ] = 20,
) -> SearchPageOutput:
    """Search within a documentation page for lines matching a query.

    Returns a compacted outline trimmed to the match range and matching lines
    with line numbers. Use the outline and match locations to identify relevant
    sections, then call read_page with the appropriate offset to read content.

    Supports literal and regex search, smart case sensitivity, and word
    boundary matching.

    Response:
      url          — the URL that was searched
      query        — the search query as provided
      outline      — compacted outline trimmed to match range; empty on zero matches
      matches      — list of {line_number, content} for matching lines
      total_lines  — total line count of the page
      has_more     — true if more matches exist beyond the returned set
      next_offset  — line number to pass as offset to continue paginating
      cached       — true if page was served from cache
      cached_at    — ISO timestamp of last fetch; null for fresh responses
    """
    state: AppState = ctx.request_context.lifespan_context
    try:
        return SearchPageOutput.model_validate(
            await t_search_page.handle(
                url,
                query,
                state,
                mode=mode,
                case_mode=case_mode,
                whole_word=whole_word,
                offset=offset,
                max_results=max_results,
            )
        )
    except ProContextError as exc:
        log.warning("tool_error", tool="search_page", code=exc.code, message=exc.message)
        raise
    except Exception:
        log.error("tool_unexpected_error", tool="search_page", exc_info=True)
        raise
