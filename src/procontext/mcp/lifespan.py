"""FastMCP lifespan: creates and tears down all shared server resources."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite
import structlog

from procontext import __version__
from procontext.cache import Cache
from procontext.config import Settings
from procontext.fetcher import Fetcher, build_allowlist, build_http_client
from procontext.registry import build_indexes, load_registry
from procontext.schedulers import (
    run_cache_cleanup_scheduler,
    run_cache_startup_cleanup,
    run_registry_startup_check,
    run_registry_update_scheduler,
)
from procontext.state import AppState

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from mcp.server.fastmcp import FastMCP

log = structlog.get_logger()


def registry_paths(settings: Settings) -> tuple[Path, Path]:
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

    registry_path, registry_state_path = registry_paths(settings)

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
    # reachable across restarts when allowlist_expansion is "discovered".
    if settings.fetcher.allowlist_expansion == "discovered":
        cached_domains = await cache.load_discovered_domains()
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
