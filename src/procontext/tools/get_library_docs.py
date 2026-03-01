"""Tool handler for get_library_docs.

Receives AppState, orchestrates cache lookup / network fetch / background
refresh, and returns a structured dict. No MCP or FastMCP imports —
server.py handles the MCP wiring.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from procontext.errors import ErrorCode, ProContextError
from procontext.fetcher import expand_allowlist_from_content
from procontext.models.tools import GetLibraryDocsInput, GetLibraryDocsOutput

if TYPE_CHECKING:
    from procontext.state import AppState


async def handle(library_id: str, state: AppState) -> dict:
    """Handle a get_library_docs tool call."""
    log = structlog.get_logger().bind(tool="get_library_docs", library_id=library_id)
    log.info("handler_called")

    # Validate input
    try:
        validated = GetLibraryDocsInput(library_id=library_id)
    except ValueError as exc:
        raise ProContextError(
            code=ErrorCode.INVALID_INPUT,
            message=str(exc),
            suggestion="Provide a valid library ID (lowercase alphanumeric, hyphens, underscores).",
            recoverable=False,
        ) from exc

    # Registry lookup
    entry = state.indexes.by_id.get(validated.library_id)
    if entry is None:
        raise ProContextError(
            code=ErrorCode.LIBRARY_NOT_FOUND,
            message=f"Library '{validated.library_id}' not found in registry.",
            suggestion="Call resolve_library with your query to find the correct library ID.",
            recoverable=False,
        )

    if state.cache is None or state.fetcher is None:
        raise RuntimeError("Phase 2 components (cache, fetcher) not initialized")

    # Cache check
    cached_entry = await state.cache.get_toc(validated.library_id)

    if cached_entry is not None and not cached_entry.stale:
        # Fresh cache hit
        log.info("cache_hit", stale=False)
        output = GetLibraryDocsOutput(
            library_id=entry.id,
            name=entry.name,
            content=cached_entry.content,
            cached=True,
            cached_at=cached_entry.fetched_at,
            stale=False,
        )
        return output.model_dump(mode="json")

    if cached_entry is not None and cached_entry.stale:
        # Stale cache hit — return immediately, refresh in background
        log.info("cache_hit", stale=True)
        asyncio.create_task(
            _background_refresh(
                library_id=entry.id,
                llms_txt_url=entry.llms_txt_url,
                state=state,
            )
        )
        output = GetLibraryDocsOutput(
            library_id=entry.id,
            name=entry.name,
            content=cached_entry.content,
            cached=True,
            cached_at=cached_entry.fetched_at,
            stale=True,
        )
        return output.model_dump(mode="json")

    # Cache miss — fetch from network
    log.info("cache_miss_fetching", url=entry.llms_txt_url)
    try:
        content = await state.fetcher.fetch(entry.llms_txt_url, state.allowlist)
    except ProContextError as exc:
        # Translate generic page-level fetch errors to llms.txt-specific error codes
        if exc.code == ErrorCode.PAGE_NOT_FOUND:
            raise ProContextError(
                code=ErrorCode.LLMS_TXT_NOT_FOUND,
                message=exc.message,
                suggestion="The llms.txt URL in the registry may be incorrect.",
                recoverable=False,
            ) from exc
        if exc.code == ErrorCode.PAGE_FETCH_FAILED:
            raise ProContextError(
                code=ErrorCode.LLMS_TXT_FETCH_FAILED,
                message=exc.message,
                suggestion="The llms.txt file may be temporarily unavailable. Try again later.",
                recoverable=True,
            ) from exc
        raise

    log.info("fetch_complete", content_length=len(content))

    # Always extract discovered domains so they're persisted regardless of depth config.
    # Whether we expand the live allowlist is controlled by allowlist_depth.
    discovered_domains = expand_allowlist_from_content(content, state, depth_threshold=1)

    # Store in cache (non-fatal on failure — handled inside Cache)
    await state.cache.set_toc(
        library_id=entry.id,
        llms_txt_url=entry.llms_txt_url,
        content=content,
        ttl_hours=state.settings.cache.ttl_hours,
        discovered_domains=discovered_domains,
    )

    output = GetLibraryDocsOutput(
        library_id=entry.id,
        name=entry.name,
        content=content,
        cached=False,
        cached_at=None,
        stale=False,
    )
    return output.model_dump(mode="json")


async def _background_refresh(
    library_id: str,
    llms_txt_url: str,
    state: AppState,
) -> None:
    """Re-fetch llms.txt in the background for stale cache entries.

    Fire-and-forget — all exceptions are caught and logged.
    """
    log = structlog.get_logger().bind(tool="get_library_docs", library_id=library_id)
    log.info("stale_refresh_started", key=f"toc:{library_id}")
    try:
        if state.fetcher is None or state.cache is None:
            log.warning("stale_refresh_skipped", reason="fetcher_or_cache_not_initialized")
            return
        content = await state.fetcher.fetch(llms_txt_url, state.allowlist)

        discovered_domains = expand_allowlist_from_content(content, state, depth_threshold=1)

        await state.cache.set_toc(
            library_id=library_id,
            llms_txt_url=llms_txt_url,
            content=content,
            ttl_hours=state.settings.cache.ttl_hours,
            discovered_domains=discovered_domains,
        )
        log.info("stale_refresh_complete", key=f"toc:{library_id}")
    except Exception:
        log.warning("stale_refresh_failed", key=f"toc:{library_id}", exc_info=True)
