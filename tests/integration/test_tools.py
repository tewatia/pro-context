"""Integration tests for MCP tool handlers.

Tests the full path through each handler: input validation → business logic
→ output serialisation. Uses a real AppState with in-memory fixtures.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from procontext.errors import ErrorCode, ProContextError
from procontext.tools.get_library_docs import handle as get_docs_handle
from procontext.tools.read_page import handle as read_page_handle
from procontext.tools.resolve_library import handle

if TYPE_CHECKING:
    from procontext.state import AppState


class TestResolveLibraryHandler:
    """Full handler pipeline tests for resolve_library."""

    async def test_valid_query_returns_match(self, app_state: AppState) -> None:
        # "langchain" is both a package name and a library ID — Step 1 wins
        result = await handle("langchain", app_state)
        assert len(result["matches"]) == 1
        match = result["matches"][0]
        assert match["library_id"] == "langchain"
        assert match["matched_via"] == "package_name"
        assert match["relevance"] == 1.0

    async def test_output_contains_all_required_fields(self, app_state: AppState) -> None:
        result = await handle("pydantic", app_state)
        match = result["matches"][0]
        assert set(match.keys()) == {
            "library_id",
            "name",
            "languages",
            "docs_url",
            "matched_via",
            "relevance",
        }

    async def test_no_match_returns_empty_list(self, app_state: AppState) -> None:
        result = await handle("xyzzy-nonexistent", app_state)
        assert result["matches"] == []

    async def test_empty_query_raises_invalid_input(self, app_state: AppState) -> None:
        with pytest.raises(ProContextError) as exc_info:
            await handle("", app_state)
        assert exc_info.value.code == ErrorCode.INVALID_INPUT
        assert exc_info.value.recoverable is False

    async def test_query_over_limit_raises_invalid_input(self, app_state: AppState) -> None:
        with pytest.raises(ProContextError) as exc_info:
            await handle("a" * 501, app_state)
        assert exc_info.value.code == ErrorCode.INVALID_INPUT
        assert exc_info.value.recoverable is False

    async def test_package_name_resolves_to_library(self, app_state: AppState) -> None:
        result = await handle("langchain-openai", app_state)
        assert result["matches"][0]["library_id"] == "langchain"
        assert result["matches"][0]["matched_via"] == "package_name"

    async def test_pip_specifier_resolves_correctly(self, app_state: AppState) -> None:
        result = await handle("langchain-openai>=0.3", app_state)
        assert result["matches"][0]["library_id"] == "langchain"


class TestGetLibraryDocsHandler:
    """Full handler pipeline tests for get_library_docs."""

    @respx.mock
    async def test_cache_miss_fetches_from_network(self, app_state: AppState) -> None:
        respx.get("https://python.langchain.com/llms.txt").mock(
            return_value=httpx.Response(200, text="# LangChain Docs\n\n## Concepts")
        )
        result = await get_docs_handle("langchain", app_state)
        assert result["library_id"] == "langchain"
        assert result["name"] == "LangChain"
        assert result["content"] == "# LangChain Docs\n\n## Concepts"
        assert result["cached"] is False
        assert result["cached_at"] is None
        assert result["stale"] is False

    @respx.mock
    async def test_cache_hit_returns_cached(self, app_state: AppState) -> None:
        respx.get("https://python.langchain.com/llms.txt").mock(
            return_value=httpx.Response(200, text="# LangChain Docs")
        )
        # First call — cache miss
        await get_docs_handle("langchain", app_state)

        # Second call — cache hit
        result = await get_docs_handle("langchain", app_state)
        assert result["cached"] is True
        assert result["cached_at"] is not None
        assert result["stale"] is False
        assert result["content"] == "# LangChain Docs"

        # Only one HTTP request was made
        assert respx.calls.call_count == 1

    async def test_unknown_library_raises_not_found(self, app_state: AppState) -> None:
        with pytest.raises(ProContextError) as exc_info:
            await get_docs_handle("nonexistent-lib", app_state)
        assert exc_info.value.code == ErrorCode.LIBRARY_NOT_FOUND
        assert exc_info.value.recoverable is False

    async def test_invalid_library_id_raises_invalid_input(self, app_state: AppState) -> None:
        with pytest.raises(ProContextError) as exc_info:
            await get_docs_handle("INVALID!!", app_state)
        assert exc_info.value.code == ErrorCode.INVALID_INPUT
        assert exc_info.value.recoverable is False

    @respx.mock
    async def test_stale_cache_returns_stale_true(self, app_state: AppState) -> None:
        respx.get("https://python.langchain.com/llms.txt").mock(
            return_value=httpx.Response(200, text="# Stale content")
        )
        # First call to populate cache
        await get_docs_handle("langchain", app_state)

        # Artificially expire the cached entry to simulate stale-while-revalidate.
        # Accesses Cache._db directly because the public API has no way to set a
        # past expiry. This couples the test to the SQLite implementation — acceptable
        # here since Cache's own unit tests cover the backend contract independently.
        from datetime import UTC, datetime, timedelta

        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        assert app_state.cache is not None
        await app_state.cache._db.execute(  # pyright: ignore[reportPrivateUsage]
            "UPDATE toc_cache SET expires_at = ? WHERE library_id = ?",
            (past, "langchain"),
        )
        await app_state.cache._db.commit()  # pyright: ignore[reportPrivateUsage]

        # Second call — stale hit
        result = await get_docs_handle("langchain", app_state)
        assert result["cached"] is True
        assert result["stale"] is True
        assert result["content"] == "# Stale content"

    @respx.mock
    async def test_output_contains_all_required_fields(self, app_state: AppState) -> None:
        respx.get("https://python.langchain.com/llms.txt").mock(
            return_value=httpx.Response(200, text="# Docs")
        )
        result = await get_docs_handle("langchain", app_state)
        assert set(result.keys()) == {
            "library_id",
            "name",
            "content",
            "cached",
            "cached_at",
            "stale",
        }

    @respx.mock
    async def test_llms_404_maps_to_llms_not_found(self, app_state: AppState) -> None:
        respx.get("https://python.langchain.com/llms.txt").mock(return_value=httpx.Response(404))
        with pytest.raises(ProContextError) as exc_info:
            await get_docs_handle("langchain", app_state)
        assert exc_info.value.code == ErrorCode.LLMS_TXT_NOT_FOUND
        assert exc_info.value.recoverable is False

    @respx.mock
    async def test_network_failure_raises_fetch_failed(self, app_state: AppState) -> None:
        respx.get("https://python.langchain.com/llms.txt").mock(return_value=httpx.Response(503))
        with pytest.raises(ProContextError) as exc_info:
            await get_docs_handle("langchain", app_state)
        assert exc_info.value.code == ErrorCode.LLMS_TXT_FETCH_FAILED
        assert exc_info.value.recoverable is True


# A small Markdown page used across read_page tests
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

        result = await read_page_handle(_SAMPLE_URL, 1, 2000, app_state)

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
        await read_page_handle(_SAMPLE_URL, 1, 2000, app_state)

        # Second call — cache hit
        result = await read_page_handle(_SAMPLE_URL, 1, 2000, app_state)
        assert result["cached"] is True
        assert result["cached_at"] is not None
        assert result["stale"] is False

        # Only one HTTP request was made
        assert respx.calls.call_count == 1

    @respx.mock
    async def test_stale_cache_returns_stale_true(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        # First call to populate cache
        await read_page_handle(_SAMPLE_URL, 1, 2000, app_state)

        # Artificially expire the cached entry to simulate stale-while-revalidate.
        # Accesses Cache._db directly because the public API has no way to set a
        # past expiry. This couples the test to the SQLite implementation — acceptable
        # here since Cache's own unit tests cover the backend contract independently.
        from datetime import UTC, datetime, timedelta

        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        assert app_state.cache is not None
        await app_state.cache._db.execute(  # pyright: ignore[reportPrivateUsage]
            "UPDATE page_cache SET expires_at = ? WHERE url = ?",
            (past, _SAMPLE_URL),
        )
        await app_state.cache._db.commit()  # pyright: ignore[reportPrivateUsage]

        # Second call — stale hit
        result = await read_page_handle(_SAMPLE_URL, 1, 2000, app_state)
        assert result["cached"] is True
        assert result["stale"] is True
        assert "# Streaming" in result["content"]

    @respx.mock
    async def test_windowing_offset_and_limit(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        # Fetch with offset=3, limit=3 — should get lines 3, 4, 5
        result = await read_page_handle(_SAMPLE_URL, 3, 3, app_state)
        lines = result["content"].split("\n")
        assert len(lines) == 3
        assert lines[0] == "## Overview"
        assert result["offset"] == 3
        assert result["limit"] == 3

    @respx.mock
    async def test_headings_always_full_page(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        # Even with a narrow window, headings reflect the full page
        result = await read_page_handle(_SAMPLE_URL, 1, 2, app_state)
        headings = result["headings"]

        # Should contain all headings, not just those in the window
        assert "## Streaming with Chains" in headings

    @respx.mock
    async def test_total_lines_correct(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        result = await read_page_handle(_SAMPLE_URL, 1, 2000, app_state)
        actual_lines = len(_SAMPLE_PAGE.splitlines())
        assert result["total_lines"] == actual_lines

    @respx.mock
    async def test_url_not_in_allowlist_raises(self, app_state: AppState) -> None:
        evil_url = "https://evil.example.com/docs.md"
        respx.get(evil_url).mock(return_value=httpx.Response(200, text="# Evil"))

        with pytest.raises(ProContextError) as exc_info:
            await read_page_handle(evil_url, 1, 2000, app_state)
        assert exc_info.value.code == ErrorCode.URL_NOT_ALLOWED
        assert exc_info.value.recoverable is False

    @respx.mock
    async def test_404_raises_page_not_found(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(404))

        with pytest.raises(ProContextError) as exc_info:
            await read_page_handle(_SAMPLE_URL, 1, 2000, app_state)
        assert exc_info.value.code == ErrorCode.PAGE_NOT_FOUND
        assert exc_info.value.recoverable is False

    @respx.mock
    async def test_network_error_raises_fetch_failed(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(503))

        with pytest.raises(ProContextError) as exc_info:
            await read_page_handle(_SAMPLE_URL, 1, 2000, app_state)
        assert exc_info.value.code == ErrorCode.PAGE_FETCH_FAILED
        assert exc_info.value.recoverable is True

    async def test_invalid_url_scheme_raises(self, app_state: AppState) -> None:
        with pytest.raises(ProContextError) as exc_info:
            await read_page_handle("ftp://example.com/docs.md", 1, 2000, app_state)
        assert exc_info.value.code == ErrorCode.INVALID_INPUT
        assert exc_info.value.recoverable is False

    async def test_url_too_long_raises(self, app_state: AppState) -> None:
        long_url = "https://example.com/" + "a" * 2040
        with pytest.raises(ProContextError) as exc_info:
            await read_page_handle(long_url, 1, 2000, app_state)
        assert exc_info.value.code == ErrorCode.INVALID_INPUT

    @respx.mock
    async def test_output_contains_all_required_fields(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        result = await read_page_handle(_SAMPLE_URL, 1, 2000, app_state)
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

        result = await read_page_handle(_SAMPLE_URL, 9999, 100, app_state)
        assert result["content"] == ""
        assert result["total_lines"] == 21
        assert result["headings"] != ""  # Headings still present
