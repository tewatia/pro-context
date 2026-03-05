"""Tool handler for read_page.

Receives AppState, orchestrates cache lookup / network fetch / heading parse /
background refresh, and returns a structured dict with windowed content.
No MCP or FastMCP imports — server.py handles the MCP wiring.
"""

from __future__ import annotations

import asyncio
import hashlib
from os.path import splitext
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlparse, urlunparse

import structlog

from procontext.errors import ErrorCode, ProContextError
from procontext.fetcher import expand_allowlist_from_content, is_url_allowed
from procontext.models.tools import ReadPageInput, ReadPageOutput
from procontext.parser import parse_outline

if TYPE_CHECKING:
    from datetime import datetime

    from procontext.state import AppState


async def handle(
    url: str,
    offset: int,
    limit: int,
    state: AppState,
    view: Literal["outline", "full"] = "full",
) -> dict:
    """Handle a read_page tool call."""
    log = structlog.get_logger().bind(tool="read_page", url=url)
    log.info("handler_called")

    # Validate input
    try:
        validated = ReadPageInput(url=url, offset=offset, limit=limit, view=view)
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
            outline=cached_entry.outline,
            offset=validated.offset,
            limit=validated.limit,
            view=validated.view,
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
            outline=cached_entry.outline,
            offset=validated.offset,
            limit=validated.limit,
            view=validated.view,
            cached=True,
            cached_at=cached_entry.fetched_at,
            stale=True,
        )

    # Cache miss — fetch from network.
    # If the URL has no file extension, try the .md variant first.
    # On any failure (404, timeout, redirect error) fall back to the original URL.
    if not _has_file_extension(validated.url):
        md_url = _with_md_extension(validated.url)
        try:
            log.info("cache_miss_fetching", url=md_url)
            content = await state.fetcher.fetch(md_url, state.allowlist)
        except Exception:
            log.info("md_probe_failed_falling_back", md_url=md_url, fallback_url=validated.url)
            log.info("cache_miss_fetching", url=validated.url)
            content = await state.fetcher.fetch(validated.url, state.allowlist)
    else:
        log.info("cache_miss_fetching", url=validated.url)
        content = await state.fetcher.fetch(validated.url, state.allowlist)
    outline = parse_outline(content)

    log.info("fetch_complete", content_length=len(content))

    # Always extract discovered domains so they're persisted regardless of depth config.
    # Whether we expand the live allowlist is controlled by allowlist_depth.
    discovered_domains = expand_allowlist_from_content(content, state, depth_threshold=2)

    # Store in cache (non-fatal on failure — handled inside Cache)
    await state.cache.set_page(
        url=validated.url,
        url_hash=url_hash,
        content=content,
        outline=outline,
        ttl_hours=state.settings.cache.ttl_hours,
        discovered_domains=discovered_domains,
    )

    return _build_output(
        url=validated.url,
        content=content,
        outline=outline,
        offset=validated.offset,
        limit=validated.limit,
        view=validated.view,
        cached=False,
        cached_at=None,
        stale=False,
    )


def _with_md_extension(url: str) -> str:
    """Return the URL with .md appended to the path component.

    Appends before any query string or fragment so the server receives the
    correct path, e.g. ``/docs/page#section`` → ``/docs/page.md#section``.
    """
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path=parsed.path + ".md"))


def _has_file_extension(url: str) -> bool:
    """Return True if the URL's last path segment has a real file extension.

    Used to decide whether to probe the .md variant — skipped when the URL
    already has any alphabetic extension (.md, .txt, .html, etc.).

    Version segments like ``v1.2`` are NOT treated as extensions because the
    part after the dot is numeric, not alphabetic.
    """
    last_segment = urlparse(url).path.rsplit("/", 1)[-1]
    _, ext = splitext(last_segment)
    return bool(ext) and ext[1:].isalpha()


def _build_output(
    *,
    url: str,
    content: str,
    outline: str,
    offset: int,
    limit: int,
    view: Literal["outline", "full"],
    cached: bool,
    cached_at: datetime | None,
    stale: bool,
) -> dict:
    """Apply line windowing and build the output dict."""
    all_lines = content.splitlines()
    total_lines = len(all_lines)

    # Window: offset is 1-based. Skipped for outline-only view.
    windowed_content: str | None
    if view == "full":
        windowed = all_lines[offset - 1 : offset - 1 + limit]
        windowed_content = "\n".join(windowed)
    else:
        windowed_content = None

    output = ReadPageOutput(
        url=url,
        outline=outline,
        total_lines=total_lines,
        offset=offset,
        limit=limit,
        content=windowed_content,
        cached=cached,
        cached_at=cached_at,
        stale=stale,
    )
    result = output.model_dump(mode="json")
    # content is intentionally absent in view="outline" responses
    if result["content"] is None:
        del result["content"]
    return result


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
        if not _has_file_extension(url):
            md_url = _with_md_extension(url)
            try:
                content = await state.fetcher.fetch(md_url, state.allowlist)
            except Exception:
                log.info("md_probe_failed_falling_back", md_url=md_url, fallback_url=url)
                content = await state.fetcher.fetch(url, state.allowlist)
        else:
            content = await state.fetcher.fetch(url, state.allowlist)
        outline = parse_outline(content)

        discovered_domains = expand_allowlist_from_content(content, state, depth_threshold=2)

        await state.cache.set_page(
            url=url,
            url_hash=url_hash,
            content=content,
            outline=outline,
            ttl_hours=state.settings.cache.ttl_hours,
            discovered_domains=discovered_domains,
        )
        log.info("stale_refresh_complete", key=f"page:{url_hash}")
    except Exception:
        log.warning("stale_refresh_failed", key=f"page:{url_hash}", exc_info=True)
