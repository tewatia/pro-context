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
import random
import re
import secrets
import sys
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite
import structlog
import uvicorn
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult, TextContent
from starlette.datastructures import Headers
from starlette.responses import Response

import procontext.tools.get_library_docs as t_get_docs
import procontext.tools.read_page as t_read_page
import procontext.tools.resolve_library as t_resolve
from procontext import __version__
from procontext.cache import Cache
from procontext.config import _DEFAULT_DATA_DIR, Settings
from procontext.errors import ProContextError
from procontext.fetcher import Fetcher, build_allowlist, build_http_client
from procontext.registry import (
    REGISTRY_INITIAL_BACKOFF_SECONDS,
    REGISTRY_MAX_BACKOFF_SECONDS,
    REGISTRY_MAX_TRANSIENT_BACKOFF_ATTEMPTS,
    build_indexes,
    check_for_registry_update,
    load_registry,
)
from procontext.state import AppState

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from starlette.types import ASGIApp, Receive, Scope, Send

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


def _registry_paths() -> tuple[Path, Path]:
    """Return local registry pair paths for the current runtime."""
    registry_dir = Path(_DEFAULT_DATA_DIR) / "registry"
    return (
        registry_dir / "known-libraries.json",
        registry_dir / "registry-state.json",
    )


FIRST_RUN_FETCH_TIMEOUT_SECONDS = 5.0


def _jittered_delay(base_seconds: int) -> float:
    return base_seconds * random.uniform(0.8, 1.2)


def _log_bundled_registry_warning() -> None:
    log.warning(
        "registry_using_bundled_snapshot",
        message=(
            "Using bundled registry snapshot. Library data may be outdated. "
            "Suggested next steps: "
            "(1) Check your internet connection. "
            "(2) Try restarting the server later. "
            "(3) If the issue persists, download the registry manually from "
            "the registry URL and place it in the data directory."
        ),
    )


async def _maybe_blocking_first_run_fetch(state: AppState) -> bool:
    """Attempt a one-shot blocking registry fetch on first run.

    Returns True if the fetch succeeded and state was updated.
    """
    try:
        outcome = await asyncio.wait_for(
            check_for_registry_update(state),
            timeout=FIRST_RUN_FETCH_TIMEOUT_SECONDS,
        )
        if outcome == "success":
            log.info("first_run_fetch_success", version=state.registry_version)
            return True
    except TimeoutError:
        log.warning("first_run_fetch_timeout", timeout=FIRST_RUN_FETCH_TIMEOUT_SECONDS)
    except Exception:
        log.warning("first_run_fetch_error", exc_info=True)

    _log_bundled_registry_warning()
    return False


async def _run_cache_cleanup_scheduler(state: AppState) -> None:
    """Run cache cleanup at startup and (HTTP mode) on the configured interval."""
    interval_hours = state.settings.cache.cleanup_interval_hours

    # Both transports: run at startup, skipping if it ran recently.
    if state.cache is not None:
        await state.cache.cleanup_if_due(interval_hours)

    if state.settings.server.transport != "http":
        return

    # HTTP long-running mode: repeat on the configured interval.
    while True:
        await asyncio.sleep(interval_hours * 3600)
        if state.cache is not None:
            await state.cache.cleanup_if_due(interval_hours)


async def _run_registry_update_scheduler(
    state: AppState,
    *,
    skip_initial_check: bool = False,
) -> None:
    """Run startup update check and (HTTP mode) periodic registry update checks."""
    if state.settings.server.transport != "http":
        if not skip_initial_check:
            try:
                await check_for_registry_update(state)
            except Exception:
                log.warning("registry_update_scheduler_error", mode="startup_once", exc_info=True)
        return

    backoff_seconds = REGISTRY_INITIAL_BACKOFF_SECONDS
    consecutive_transient_failures = 0

    while True:
        try:
            outcome = await check_for_registry_update(state)
        except Exception:
            log.warning("registry_update_scheduler_error", mode="http_loop", exc_info=True)
            outcome = "semantic_failure"

        poll_interval_seconds = state.settings.registry.poll_interval_hours * 3600

        if outcome == "success":
            consecutive_transient_failures = 0
            backoff_seconds = REGISTRY_INITIAL_BACKOFF_SECONDS
            await asyncio.sleep(poll_interval_seconds)
            continue

        if outcome == "transient_failure":
            consecutive_transient_failures += 1
            if consecutive_transient_failures >= REGISTRY_MAX_TRANSIENT_BACKOFF_ATTEMPTS:
                log.warning(
                    "registry_update_transient_retry_suspended",
                    consecutive_failures=consecutive_transient_failures,
                    cooldown_seconds=poll_interval_seconds,
                )
                consecutive_transient_failures = 0
                backoff_seconds = REGISTRY_INITIAL_BACKOFF_SECONDS
                await asyncio.sleep(poll_interval_seconds)
                continue

            await asyncio.sleep(_jittered_delay(backoff_seconds))
            backoff_seconds = min(backoff_seconds * 2, REGISTRY_MAX_BACKOFF_SECONDS)
            continue

        # semantic failure
        consecutive_transient_failures = 0
        backoff_seconds = REGISTRY_INITIAL_BACKOFF_SECONDS
        await asyncio.sleep(poll_interval_seconds)


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncGenerator[AppState, None]:
    """Create and tear down all shared resources for the server's lifetime."""
    settings = Settings()
    _setup_logging(settings)

    log.info(
        "server_starting",
        version=__version__,
        transport=settings.server.transport,
    )

    registry_path, registry_state_path = _registry_paths()

    # Phase 1: Load registry and build indexes
    entries, version = load_registry(
        local_registry_path=registry_path,
        local_state_path=registry_state_path,
    )
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

    # First run (bundled fallback): attempt a blocking fetch before serving
    first_run_attempted = False
    if version == "unknown":
        first_run_attempted = True
        await _maybe_blocking_first_run_fetch(state)

    registry_update_task = asyncio.create_task(
        _run_registry_update_scheduler(state, skip_initial_check=first_run_attempted)
    )
    cache_cleanup_task = asyncio.create_task(_run_cache_cleanup_scheduler(state))

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
# HTTP transport
# ---------------------------------------------------------------------------

SUPPORTED_PROTOCOL_VERSIONS: frozenset[str] = frozenset({"2025-11-25", "2025-03-26"})
_LOCALHOST_ORIGIN = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")


class MCPSecurityMiddleware:
    """Pure ASGI middleware for HTTP transport security.

    Enforces three checks on every HTTP request:
    1. Optional bearer key authentication.
    2. Origin validation (localhost only) to prevent DNS rebinding.
    3. Protocol version validation via MCP-Protocol-Version header.

    Implemented as pure ASGI (not BaseHTTPMiddleware) so that SSE streaming
    responses are never buffered by the middleware layer.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        auth_enabled: bool,
        auth_key: str | None = None,
    ) -> None:
        self.app = app
        self.auth_enabled = auth_enabled
        self.auth_key = auth_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = Headers(scope=scope)

            # 1. Optional bearer key authentication
            if self.auth_enabled:
                auth_header = headers.get("authorization", "")
                if not auth_header.startswith("Bearer ") or auth_header[7:] != self.auth_key:
                    await Response("Unauthorized", status_code=401)(scope, receive, send)
                    return

            # 2. Origin validation — prevents DNS rebinding attacks
            origin = headers.get("origin", "")
            if origin and not _LOCALHOST_ORIGIN.match(origin):
                await Response("Forbidden", status_code=403)(scope, receive, send)
                return

            # 3. Protocol version — reject unknown versions early
            proto_version = headers.get("mcp-protocol-version", "")
            if proto_version and proto_version not in SUPPORTED_PROTOCOL_VERSIONS:
                await Response(
                    f"Unsupported protocol version: {proto_version}",
                    status_code=400,
                )(scope, receive, send)
                return

        await self.app(scope, receive, send)


def run_http_server(settings: Settings) -> None:
    """Start the MCP server with Streamable HTTP transport."""
    _setup_logging(settings)
    http_log = structlog.get_logger().bind(transport="http")

    auth_key: str | None = settings.server.auth_key or None

    if settings.server.auth_enabled and not auth_key:
        auth_key = secrets.token_urlsafe(32)
        http_log.warning("http_auth_key_auto_generated", auth_key=auth_key)

    if not settings.server.auth_enabled:
        http_log.warning("http_auth_disabled")

    http_app = mcp.streamable_http_app()
    secured_app = MCPSecurityMiddleware(
        http_app,
        auth_enabled=settings.server.auth_enabled,
        auth_key=auth_key,
    )

    uvicorn.run(
        secured_app,
        host=settings.server.host,
        port=settings.server.port,
        log_config=None,  # Disable uvicorn's default logging; structlog handles it
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    settings = Settings()

    if settings.server.transport == "http":
        run_http_server(settings)
        return

    mcp.run()


if __name__ == "__main__":
    main()
