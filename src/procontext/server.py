"""MCP server entrypoint.

Responsibilities (and nothing more):
- Configure structlog
- Create AppState via the FastMCP lifespan context manager
- Register tools
- Start the correct transport (stdio or HTTP)
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite
import structlog
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult, TextContent

import procontext.tools.get_library_docs as t_get_docs
import procontext.tools.read_page as t_read_page
import procontext.tools.resolve_library as t_resolve
from procontext import __version__
from procontext.cache import Cache
from procontext.config import Settings
from procontext.errors import ProContextError
from procontext.fetcher import Fetcher, build_allowlist, build_http_client
from procontext.registry import build_indexes, fetch_registry_for_setup, load_registry
from procontext.schedulers import run_cache_cleanup_scheduler, run_registry_update_scheduler
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
        processors = [*shared_processors, structlog.processors.JSONRenderer()]
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

    # Phase 1: Load registry and build indexes
    registry = load_registry(
        local_registry_path=registry_path,
        local_state_path=registry_state_path,
    )
    auto_setup_ran = False
    if registry is None:
        log.info("registry_not_found_attempting_auto_setup")
        await _attempt_registry_setup(settings, registry_path, registry_state_path)
        registry = load_registry(
            local_registry_path=registry_path, local_state_path=registry_state_path
        )
        auto_setup_ran = registry is not None

    if registry is None:
        print(
            "\nRegistry not initialised. Run 'procontext setup' to download the registry.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    entries, version = registry
    indexes = build_indexes(entries)

    # Phase 2: HTTP client, SSRF allowlist, cache, fetcher
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

    registry_update_task = asyncio.create_task(
        run_registry_update_scheduler(state, skip_initial_check=auto_setup_ran)
    )
    cache_cleanup_task = asyncio.create_task(run_cache_cleanup_scheduler(state))

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


def _serialise_tool_error(error: ProContextError) -> CallToolResult:
    """Convert a ProContextError to the MCP tool error result envelope."""
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(error.to_dict()))],
        isError=True,
    )


@mcp.tool()
async def resolve_library(query: str, ctx: Context) -> object:
    """Resolve a library name or package name to a known documentation source."""
    state: AppState = ctx.request_context.lifespan_context
    try:
        return await t_resolve.handle(query, state)
    except ProContextError as exc:
        log.warning(
            "tool_error",
            tool="resolve_library",
            code=exc.code,
            message=exc.message,
            recoverable=exc.recoverable,
        )
        return _serialise_tool_error(exc)
    except Exception:
        log.error("tool_unexpected_error", tool="resolve_library", exc_info=True)
        raise


@mcp.tool()
async def get_library_docs(library_id: str, ctx: Context) -> object:
    """Fetch the llms.txt table of contents for a library."""
    state: AppState = ctx.request_context.lifespan_context
    try:
        return await t_get_docs.handle(library_id, state)
    except ProContextError as exc:
        log.warning(
            "tool_error",
            tool="get_library_docs",
            code=exc.code,
            message=exc.message,
            recoverable=exc.recoverable,
        )
        return _serialise_tool_error(exc)
    except Exception:
        log.error("tool_unexpected_error", tool="get_library_docs", exc_info=True)
        raise


@mcp.tool()
async def read_page(url: str, ctx: Context, offset: int = 1, limit: int = 2000) -> object:
    """Fetch the content of a documentation page.

    Returns a plain-text heading map (line numbers + heading text) for the full
    page, and a content window controlled by offset and limit. Use headings to
    find sections, then call again with offset to jump directly to them.
    """
    state: AppState = ctx.request_context.lifespan_context
    try:
        return await t_read_page.handle(url, offset, limit, state)
    except ProContextError as exc:
        log.warning(
            "tool_error",
            tool="read_page",
            code=exc.code,
            message=exc.message,
            recoverable=exc.recoverable,
        )
        return _serialise_tool_error(exc)
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
        print("Setup failed. Check your network and try again.", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    settings = Settings()
    _setup_logging(settings)

    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        asyncio.run(_run_setup(settings))
        return

    if settings.server.transport == "http":
        run_http_server(mcp, settings)
        return

    mcp.run()


if __name__ == "__main__":
    main()
