"""MCP tool registrations.

Defines the FastMCP instance and registers the ProContext tools.
Startup, logging setup, and lifespan management live in their own modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

import structlog
from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

import procontext.tools.read_page as t_read_page
import procontext.tools.resolve_library as t_resolve
from procontext import __version__
from procontext.errors import ProContextError
from procontext.mcp.lifespan import lifespan
from procontext.models.tools import ReadPageOutput, ResolveLibraryOutput

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
    Then pass the llms_txt_url to read_page to get the documentation index.

    Response:
      matches        — ranked list of results, sorted by relevance descending
      Each match contains:
        library_id   — canonical library identifier
        name         — human-readable library name
        llms_txt_url — URL of the documentation index (pass to read_page)
        docs_url     — documentation site URL (may be null)
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
    view: Annotated[
        Literal["outline", "full"],
        Field(
            description=(
                "outline: returns page outline and total_lines only, no page content. "
                "full: returns page outline plus content window based on offset and limit."
            )
        ),
    ] = "full",
) -> ReadPageOutput:
    """Fetch the outline and content of a documentation page.

    Accepts any documentation URL — typically the llms_txt_url from
    resolve_library or a link found within a previously fetched page.

    Navigation patterns:
      Pattern 1 (default) — call with view="full". Use outline line numbers
      to identify the section you need, then call again with offset=<line>.

      Pattern 2 — call with view="outline" across several candidate pages to
      compare structure cheaply before committing to a full read.

    Response:
      url          — the URL of the fetched page
      outline      — H1–H6 headings and fence markers with 1-based line
                     numbers, e.g. "1: # Title\\n42: ## Usage". Always the
                     full page outline regardless of offset/limit.
      total_lines  — total line count of the full page; always present
      offset       — 1-based line number where the content window starts
      limit        — maximum lines in the content window
      content      — the content window (view="full" only; absent for view="outline")
      cached       — true if served from cache
      cached_at    — ISO timestamp of last fetch; null for fresh network responses
      stale        — true if cache entry is expired; background refresh in progress

    If offset + limit < total_lines, there is more content — call again with
    a higher offset to continue reading. Repeated calls on the same URL are
    served from cache (sub-100ms).
    """
    state: AppState = ctx.request_context.lifespan_context
    try:
        return ReadPageOutput.model_validate(
            await t_read_page.handle(url, offset, limit, state, view=view)
        )
    except ProContextError as exc:
        log.warning("tool_error", tool="read_page", code=exc.code, message=exc.message)
        raise
    except Exception:
        log.error("tool_unexpected_error", tool="read_page", exc_info=True)
        raise
