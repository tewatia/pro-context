"""Shared fixtures and helpers for tool integration tests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from procontext.cache import Cache

if TYPE_CHECKING:
    from procontext.state import AppState


SAMPLE_PAGE = """\
# Streaming

## Overview

LangChain supports streaming.

## Streaming with Chat Models

Details here.

### Using .stream()

The `.stream()` method returns an iterator.

### Using .astream()

The `.astream()` method is async.

## Streaming with Chains

Chain streaming details."""

SAMPLE_URL = "https://python.langchain.com/docs/concepts/streaming.md"


async def expire_cached_page(
    app_state: AppState,
    *,
    url: str = SAMPLE_URL,
    last_checked_at: str | None = None,
) -> None:
    """Mark a cached page stale, optionally preserving last_checked_at."""
    stale_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    assert isinstance(app_state.cache, Cache)
    await app_state.cache._db.execute(  # pyright: ignore[reportPrivateUsage]
        "UPDATE page_cache SET expires_at = ?, last_checked_at = ? WHERE url = ?",
        (stale_time, last_checked_at, url),
    )
    await app_state.cache._db.commit()  # pyright: ignore[reportPrivateUsage]


def hashed_url(url: str = SAMPLE_URL) -> str:
    """Return the internal URL hash used for background refresh tracking."""
    return hashlib.sha256(url.encode()).hexdigest()


async def update_cached_page_content(
    app_state: AppState,
    content: str,
    *,
    url: str = SAMPLE_URL,
) -> None:
    """Overwrite cached content for a page."""
    assert isinstance(app_state.cache, Cache)
    await app_state.cache._db.execute(  # pyright: ignore[reportPrivateUsage]
        "UPDATE page_cache SET content = ? WHERE url = ?",
        (content, url),
    )
    await app_state.cache._db.commit()  # pyright: ignore[reportPrivateUsage]
