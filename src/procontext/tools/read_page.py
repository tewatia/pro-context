"""Tool handler for read_page.

Receives AppState, orchestrates cache lookup / network fetch / heading parse /
background refresh, and returns a structured dict with windowed content.
No MCP or FastMCP imports — server.py handles the MCP wiring.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import TYPE_CHECKING

import structlog

from procontext.errors import ErrorCode, ProContextError
from procontext.fetcher import expand_allowlist_from_content, is_url_allowed
from procontext.models.tools import ReadPageInput, ReadPageOutput
from procontext.parser import parse_headings

if TYPE_CHECKING:
    from datetime import datetime

    from procontext.state import AppState


async def handle(url: str, offset: int, limit: int, state: AppState) -> dict:
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

    if state.cache is None or state.fetcher is None:
        raise RuntimeError("Phase 2 components (cache, fetcher) not initialized")

    # SSRF check — must happen before cache lookup so that pages from
    # domains removed from the allowlist are not served from cache.
    if not is_url_allowed(
        validated.url,
        state.allowlist,
        check_private_ips=state.settings.fetcher.ssrf_private_ip_check,
        check_domain=state.settings.fetcher.ssrf_domain_check,
    ):
        log.warning("ssrf_blocked", url=validated.url, reason="not_in_allowlist")
        raise ProContextError(
            code=ErrorCode.URL_NOT_ALLOWED,
            message=f"URL not in allowlist: {validated.url}",
            suggestion="Only URLs from known documentation domains are permitted.",
            recoverable=False,
        )

    url_hash = hashlib.sha256(validated.url.encode()).hexdigest()

    # Cache check
    cached_entry = await state.cache.get_page(url_hash)

    if cached_entry is not None and not cached_entry.stale:
        # Fresh cache hit
        log.info("cache_hit", stale=False)
        return _build_output(
            url=cached_entry.url,
            content=cached_entry.content,
            headings=cached_entry.headings,
            offset=validated.offset,
            limit=validated.limit,
            cached=True,
            cached_at=cached_entry.fetched_at,
            stale=False,
        )

    if cached_entry is not None and cached_entry.stale:
        # Stale cache hit — return immediately, refresh in background
        log.info("cache_hit", stale=True)
        asyncio.create_task(
            _background_refresh(
                url=cached_entry.url,
                url_hash=url_hash,
                state=state,
            )
        )
        return _build_output(
            url=cached_entry.url,
            content=cached_entry.content,
            headings=cached_entry.headings,
            offset=validated.offset,
            limit=validated.limit,
            cached=True,
            cached_at=cached_entry.fetched_at,
            stale=True,
        )

    # Cache miss — fetch from network
    log.info("cache_miss_fetching", url=validated.url)
    content = await state.fetcher.fetch(validated.url, state.allowlist)
    headings = parse_headings(content)

    log.info("fetch_complete", content_length=len(content))

    # Always extract discovered domains so they're persisted regardless of depth config.
    # Whether we expand the live allowlist is controlled by allowlist_depth.
    discovered_domains = expand_allowlist_from_content(content, state, depth_threshold=2)

    # Store in cache (non-fatal on failure — handled inside Cache)
    await state.cache.set_page(
        url=validated.url,
        url_hash=url_hash,
        content=content,
        headings=headings,
        ttl_hours=state.settings.cache.ttl_hours,
        discovered_domains=discovered_domains,
    )

    return _build_output(
        url=validated.url,
        content=content,
        headings=headings,
        offset=validated.offset,
        limit=validated.limit,
        cached=False,
        cached_at=None,
        stale=False,
    )


def _build_output(
    *,
    url: str,
    content: str,
    headings: str,
    offset: int,
    limit: int,
    cached: bool,
    cached_at: datetime | None,
    stale: bool,
) -> dict:
    """Apply line windowing and build the output dict."""
    all_lines = content.splitlines()
    total_lines = len(all_lines)

    # Window: offset is 1-based
    windowed = all_lines[offset - 1 : offset - 1 + limit]
    windowed_content = "\n".join(windowed)

    output = ReadPageOutput(
        url=url,
        headings=headings,
        total_lines=total_lines,
        offset=offset,
        limit=limit,
        content=windowed_content,
        cached=cached,
        cached_at=cached_at,
        stale=stale,
    )
    return output.model_dump(mode="json")


async def _background_refresh(
    url: str,
    url_hash: str,
    state: AppState,
) -> None:
    """Re-fetch a page in the background for stale cache entries.

    Fire-and-forget — all exceptions are caught and logged.
    """
    log = structlog.get_logger().bind(tool="read_page", url=url)
    log.info("stale_refresh_started", key=f"page:{url_hash}")
    try:
        if state.fetcher is None or state.cache is None:
            log.warning("stale_refresh_skipped", reason="fetcher_or_cache_not_initialized")
            return
        content = await state.fetcher.fetch(url, state.allowlist)
        headings = parse_headings(content)

        discovered_domains = expand_allowlist_from_content(content, state, depth_threshold=2)

        await state.cache.set_page(
            url=url,
            url_hash=url_hash,
            content=content,
            headings=headings,
            ttl_hours=state.settings.cache.ttl_hours,
            discovered_domains=discovered_domains,
        )
        log.info("stale_refresh_complete", key=f"page:{url_hash}")
    except Exception:
        log.warning("stale_refresh_failed", key=f"page:{url_hash}", exc_info=True)
