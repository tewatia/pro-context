"""MCP server entrypoint.

Responsibilities (and nothing more):
- Configure structlog
- Create AppState via the FastMCP lifespan context manager
- Register tools
- Start the correct transport (stdio or HTTP)
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from mcp.server.fastmcp import Context, FastMCP

import pro_context.tools.resolve_library as t_resolve
from pro_context import __version__
from pro_context.config import Settings
from pro_context.registry import build_indexes, load_registry
from pro_context.state import AppState

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

    # Phase 1: Load registry and build indexes
    entries, version = load_registry()
    indexes = build_indexes(entries)

    state = AppState(
        settings=settings,
        indexes=indexes,
        registry_version=version,
    )

    log.info(
        "server_started",
        version=__version__,
        transport=settings.server.transport,
        registry_entries=len(entries),
        registry_version=version,
    )

    try:
        yield state
    finally:
        log.info("server_stopping")


# ---------------------------------------------------------------------------
# FastMCP instance and tool registration
# ---------------------------------------------------------------------------

mcp = FastMCP("pro-context", lifespan=lifespan)


@mcp.tool()
async def resolve_library(query: str, ctx: Context) -> dict:
    """Resolve a library name or package name to a known documentation source."""
    state: AppState = ctx.request_context.lifespan_context
    return await t_resolve.handle(query, state)


# Phase 2 — get_library_docs
# Phase 3 — read_page


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    settings = Settings()

    if settings.server.transport == "http":
        # HTTP transport is implemented in Phase 4.
        # Fail loudly so the operator knows what to do.
        print(
            "ERROR: HTTP transport is not yet implemented. "
            "Set transport: stdio in pro-context.yaml or unset PRO_CONTEXT__SERVER__TRANSPORT.",
            file=sys.stderr,
        )
        sys.exit(1)

    mcp.run()


if __name__ == "__main__":
    main()
