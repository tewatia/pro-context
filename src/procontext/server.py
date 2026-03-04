"""MCP server entrypoint.

Responsibilities (and nothing more):
- Configure structlog
- Create AppState via the FastMCP lifespan context manager
- Register tools
- Start the correct transport (stdio or HTTP)
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

import aiosqlite
import structlog
from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field, ValidationError

import procontext.tools.get_library_docs as t_get_docs
import procontext.tools.read_page as t_read_page
import procontext.tools.resolve_library as t_resolve
from procontext import __version__
from procontext.cache import Cache
from procontext.config import Settings
from procontext.errors import ProContextError
from procontext.fetcher import Fetcher, build_allowlist, build_http_client
from procontext.models.tools import GetLibraryDocsOutput, ReadPageOutput, ResolveLibraryOutput
from procontext.registry import build_indexes, fetch_registry_for_setup, load_registry
from procontext.schedulers import (
    run_cache_cleanup_scheduler,
    run_cache_startup_cleanup,
    run_registry_startup_check,
    run_registry_update_scheduler,
)
from procontext.state import AppState
from procontext.transport import run_http_server

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def _setup_logging(settings: Settings) -> None:
    """Configure structlog. Called once at startup before any log statements."""
    log_level = logging.getLevelNamesMapping()[settings.logging.level]

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if settings.logging.format == "json":
        processors = [
            *shared_processors,
            structlog.processors.ExceptionRenderer(),
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = [*shared_processors, structlog.dev.ConsoleRenderer()]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        # Logs go to stderr — stdout is reserved for the MCP JSON-RPC stream
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


def _registry_paths(settings: Settings) -> tuple[Path, Path]:
    """Return local registry pair paths for the current runtime."""
    registry_dir = Path(settings.data_dir) / "registry"
    return (
        registry_dir / "known-libraries.json",
        registry_dir / "registry-state.json",
    )


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncGenerator[AppState, None]:
    """Create and tear down all shared resources for the server's lifetime."""
    settings = Settings()

    log.info(
        "server_starting",
        version=__version__,
        transport=settings.server.transport,
    )

    registry_path, registry_state_path = _registry_paths(settings)

    # Registry availability is guaranteed by main() before the server starts.
    registry = load_registry(
        local_registry_path=registry_path,
        local_state_path=registry_state_path,
    )
    if registry is None:
        raise RuntimeError(
            "Registry unavailable at server startup — this should have been caught before "
            "the server started. This is a bug."
        )

    entries, version = registry
    indexes = build_indexes(entries)

    http_client = build_http_client(settings.fetcher)
    allowlist = build_allowlist(entries, extra_domains=settings.fetcher.extra_allowed_domains)

    db_path = Path(settings.cache.db_path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(db_path))
    cache = Cache(db)
    await cache.init_db()

    # Restore domains discovered in previous sessions so cache hits remain
    # reachable across restarts when allowlist_depth > 0.
    if settings.fetcher.allowlist_depth > 0:
        cached_domains = await cache.load_discovered_domains(
            include_toc=settings.fetcher.allowlist_depth >= 1,
            include_pages=settings.fetcher.allowlist_depth >= 2,
        )
        if cached_domains:
            allowlist = allowlist | cached_domains
            log.info("allowlist_restored_from_cache", domain_count=len(cached_domains))

    fetcher = Fetcher(http_client, settings.fetcher)

    state = AppState(
        settings=settings,
        indexes=indexes,
        registry_version=version,
        registry_path=registry_path,
        registry_state_path=registry_state_path,
        http_client=http_client,
        cache=cache,
        fetcher=fetcher,
        allowlist=allowlist,
    )

    if settings.server.transport == "http":
        registry_update_task = asyncio.create_task(run_registry_update_scheduler(state))
        cache_cleanup_task = asyncio.create_task(run_cache_cleanup_scheduler(state))
    else:
        registry_update_task = asyncio.create_task(run_registry_startup_check(state))
        cache_cleanup_task = asyncio.create_task(run_cache_startup_cleanup(state))

    log.info(
        "server_started",
        version=__version__,
        transport=settings.server.transport,
        registry_entries=len(state.indexes.by_id),
        registry_version=state.registry_version,
    )

    try:
        yield state
    finally:
        registry_update_task.cancel()
        cache_cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await registry_update_task
        with suppress(asyncio.CancelledError):
            await cache_cleanup_task
        await http_client.aclose()
        await db.close()
        log.info("server_stopping")


# ---------------------------------------------------------------------------
# FastMCP instance and tool registration
# ---------------------------------------------------------------------------

mcp = FastMCP("procontext", lifespan=lifespan)
# FastMCP doesn't expose a version kwarg — set it on the underlying Server
# so the MCP initialize handshake reports our version, not the SDK's.
mcp._mcp_server.version = __version__  # pyright: ignore[reportPrivateUsage]


@mcp.tool()
async def resolve_library(
    query: Annotated[
        str,
        Field(
            description=("Library name, package specifier (e.g. 'langchain-community'), or alias.")
        ),
    ],
    ctx: Context,
) -> ResolveLibraryOutput:
    """Resolve a library name to its documentation source.

    Returns a ranked list of matches sorted by relevance; the top match is almost always
    correct. Matched in priority order: exact PyPI/npm package names, canonical library IDs,
    registered aliases, then fuzzy name matching.

    Always call this first to obtain a library_id, then pass it to get_library_index.
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
async def get_library_index(
    library_id: Annotated[
        str,
        Field(description="Library ID returned by resolve_library."),
    ],
    ctx: Context,
) -> GetLibraryDocsOutput:
    """Fetch the table of contents for a library's documentation.

    Returns raw markdown containing URLs to specific documentation pages.
    Pass these URLs to read_page to fetch a specific page.

    stale=true means the content was served from an expired cache entry and
    is being refreshed in the background; it is still usable.
    """
    state: AppState = ctx.request_context.lifespan_context
    try:
        return GetLibraryDocsOutput.model_validate(await t_get_docs.handle(library_id, state))
    except ProContextError as exc:
        log.warning("tool_error", tool="get_library_index", code=exc.code, message=exc.message)
        raise
    except Exception:
        log.error("tool_unexpected_error", tool="get_library_index", exc_info=True)
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

    Accepts any documentation URL — from get_library_index or linked within a page
    from read_page content.

    Navigation patterns:
      Pattern 1 — call with view="full", then scroll through using offset
      or use outline line numbers to jump directly to specific sections.

      Pattern 2 — call view="outline" across pages from get_library_index
      to compare structure cheaply before committing to a full read. Useful
      when skimming multiple pages to find the right one.

    Pattern 1 is the recommended default.
    Repeated calls on the same URL are served from cache (sub-100ms).
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


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


async def _attempt_registry_setup(
    settings: Settings,
    registry_path: Path,
    registry_state_path: Path,
) -> bool:
    """Try to fetch and persist the registry once. Returns True on success."""
    http_client = build_http_client(settings.fetcher)
    try:
        return await fetch_registry_for_setup(
            http_client=http_client,
            metadata_url=settings.registry.metadata_url,
            registry_path=registry_path,
            registry_state_path=registry_state_path,
        )
    finally:
        await http_client.aclose()


async def _ensure_registry(settings: Settings) -> bool:
    """Check registry availability, attempt auto-setup if needed. Returns True if ready."""
    registry_path, registry_state_path = _registry_paths(settings)
    if load_registry(local_registry_path=registry_path, local_state_path=registry_state_path):
        return True
    log.info("registry_not_found_attempting_auto_setup")
    await _attempt_registry_setup(settings, registry_path, registry_state_path)
    return (
        load_registry(local_registry_path=registry_path, local_state_path=registry_state_path)
        is not None
    )


async def _run_setup(settings: Settings) -> None:
    """Fetch the registry from the configured URL and save it to the data directory."""
    registry_path, registry_state_path = _registry_paths(settings)

    print(f"Downloading registry from {settings.registry.metadata_url} ...", flush=True)

    if await _attempt_registry_setup(settings, registry_path, registry_state_path):
        print(
            f"Registry initialised (saved to: {registry_path})",
            flush=True,
        )
    else:
        print(
            """Setup failed. Check your network and try again.
If the error persists, you can manually download the registry,
and configure its path in procontext.yaml""",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    try:
        settings = Settings()
    except ValidationError as exc:
        print(f"Configuration error:\n{exc}", file=sys.stderr)
        sys.exit(1)
    _setup_logging(settings)

    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        asyncio.run(_run_setup(settings))
        return

    if not asyncio.run(_ensure_registry(settings)):
        log.critical(
            "registry_not_initialised",
            hint="Run 'procontext setup' to download the registry.",
        )
        sys.exit(1)

    if settings.server.transport == "http":
        run_http_server(mcp, settings)
        return

    mcp.run()


if __name__ == "__main__":
    main()
