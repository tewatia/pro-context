"""Integration tests for the read_page tool handler.

Tests the full path: input validation → cache lookup → fetch → parse headings
→ windowing → output serialisation.  Uses a real AppState with in-memory fixtures.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from procontext.errors import ErrorCode, ProContextError
from procontext.tools.read_page import handle

if TYPE_CHECKING:
    from procontext.state import AppState

# A small Markdown page used across multiple tests
_SAMPLE_PAGE = """\
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

_SAMPLE_URL = "https://python.langchain.com/docs/concepts/streaming.md"


class TestReadPageHandler:
    """Full handler pipeline tests for read_page."""

    @respx.mock
    async def test_cache_miss_fetches_and_returns(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        result = await handle(_SAMPLE_URL, 1, 2000, app_state)

        assert result["url"] == _SAMPLE_URL
        assert result["cached"] is False
        assert result["cached_at"] is None
        assert result["stale"] is False
        assert result["total_lines"] == 21
        assert "# Streaming" in result["headings"]
        assert "## Overview" in result["headings"]
        assert "# Streaming" in result["content"]

    @respx.mock
    async def test_cache_hit_returns_cached(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        # First call — cache miss
        await handle(_SAMPLE_URL, 1, 2000, app_state)

        # Second call — cache hit
        result = await handle(_SAMPLE_URL, 1, 2000, app_state)
        assert result["cached"] is True
        assert result["cached_at"] is not None
        assert result["stale"] is False

        # Only one HTTP request was made
        assert respx.calls.call_count == 1

    @respx.mock
    async def test_stale_cache_returns_stale_true(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        # First call to populate cache
        await handle(_SAMPLE_URL, 1, 2000, app_state)

        # Manually expire the cached entry
        from datetime import UTC, datetime, timedelta

        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        assert app_state.cache is not None
        await app_state.cache._db.execute(
            "UPDATE page_cache SET expires_at = ? WHERE url = ?",
            (past, _SAMPLE_URL),
        )
        await app_state.cache._db.commit()

        # Second call — stale hit
        result = await handle(_SAMPLE_URL, 1, 2000, app_state)
        assert result["cached"] is True
        assert result["stale"] is True
        assert "# Streaming" in result["content"]

    @respx.mock
    async def test_windowing_offset_and_limit(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        # Fetch with offset=3, limit=3 — should get lines 3, 4, 5
        result = await handle(_SAMPLE_URL, 3, 3, app_state)
        lines = result["content"].split("\n")
        assert len(lines) == 3
        assert lines[0] == "## Overview"
        assert result["offset"] == 3
        assert result["limit"] == 3

    @respx.mock
    async def test_headings_always_full_page(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        # Even with a narrow window, headings reflect the full page
        result = await handle(_SAMPLE_URL, 1, 2, app_state)
        headings = result["headings"]

        # Should contain all headings, not just those in the window
        assert "## Streaming with Chains" in headings

    @respx.mock
    async def test_total_lines_correct(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        result = await handle(_SAMPLE_URL, 1, 2000, app_state)
        actual_lines = len(_SAMPLE_PAGE.splitlines())
        assert result["total_lines"] == actual_lines

    @respx.mock
    async def test_url_not_in_allowlist_raises(self, app_state: AppState) -> None:
        evil_url = "https://evil.example.com/docs.md"
        respx.get(evil_url).mock(return_value=httpx.Response(200, text="# Evil"))

        with pytest.raises(ProContextError) as exc_info:
            await handle(evil_url, 1, 2000, app_state)
        assert exc_info.value.code == ErrorCode.URL_NOT_ALLOWED
        assert exc_info.value.recoverable is False

    @respx.mock
    async def test_404_raises_page_not_found(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(404))

        with pytest.raises(ProContextError) as exc_info:
            await handle(_SAMPLE_URL, 1, 2000, app_state)
        assert exc_info.value.code == ErrorCode.PAGE_NOT_FOUND
        assert exc_info.value.recoverable is False

    @respx.mock
    async def test_network_error_raises_fetch_failed(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(503))

        with pytest.raises(ProContextError) as exc_info:
            await handle(_SAMPLE_URL, 1, 2000, app_state)
        assert exc_info.value.code == ErrorCode.PAGE_FETCH_FAILED
        assert exc_info.value.recoverable is True

    async def test_invalid_url_scheme_raises(self, app_state: AppState) -> None:
        with pytest.raises(ProContextError) as exc_info:
            await handle("ftp://example.com/docs.md", 1, 2000, app_state)
        assert exc_info.value.code == ErrorCode.INVALID_INPUT
        assert exc_info.value.recoverable is False

    async def test_url_too_long_raises(self, app_state: AppState) -> None:
        long_url = "https://example.com/" + "a" * 2040
        with pytest.raises(ProContextError) as exc_info:
            await handle(long_url, 1, 2000, app_state)
        assert exc_info.value.code == ErrorCode.INVALID_INPUT

    @respx.mock
    async def test_output_contains_all_required_fields(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        result = await handle(_SAMPLE_URL, 1, 2000, app_state)
        assert set(result.keys()) == {
            "url",
            "headings",
            "total_lines",
            "offset",
            "limit",
            "content",
            "cached",
            "cached_at",
            "stale",
        }

    @respx.mock
    async def test_offset_beyond_content_returns_empty(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        result = await handle(_SAMPLE_URL, 9999, 100, app_state)
        assert result["content"] == ""
        assert result["total_lines"] == 21
        assert result["headings"] != ""  # Headings still present
