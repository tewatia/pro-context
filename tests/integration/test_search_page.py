"""Integration tests for the search_page tool handler."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from procontext.errors import ErrorCode, ProContextError
from procontext.tools.read_page import handle as read_page_handle
from procontext.tools.search_page import handle as search_page_handle
from tests.integration.tool_test_support import SAMPLE_PAGE, SAMPLE_URL

if TYPE_CHECKING:
    from procontext.state import AppState


class TestSearchPageHandler:
    """Full handler pipeline tests for search_page."""

    @respx.mock
    async def test_search_cache_miss_returns_matches(self, app_state: AppState) -> None:
        respx.get(SAMPLE_URL).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        result = await search_page_handle(SAMPLE_URL, "streaming", app_state)

        assert result["url"] == SAMPLE_URL
        assert result["query"] == "streaming"
        assert result["cached"] is False
        assert result["matches"] != ""
        for line in result["matches"].split("\n"):
            colon_index = line.index(":")
            int(line[:colon_index])

    @respx.mock
    async def test_search_cache_hit_shared_with_read_page(self, app_state: AppState) -> None:
        """read_page populates cache, search_page uses it with no extra fetch."""
        respx.get(SAMPLE_URL).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        await read_page_handle(SAMPLE_URL, 1, 500, app_state)
        assert respx.calls.call_count == 1

        result = await search_page_handle(SAMPLE_URL, "streaming", app_state)
        assert result["cached"] is True
        assert respx.calls.call_count == 1

    @respx.mock
    async def test_search_invalid_regex_raises(self, app_state: AppState) -> None:
        respx.get(SAMPLE_URL).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        with pytest.raises(ProContextError) as exc_info:
            await search_page_handle(SAMPLE_URL, "[invalid", app_state, mode="regex")
        assert exc_info.value.code == ErrorCode.INVALID_INPUT

    @respx.mock
    async def test_search_no_matches_returns_empty(self, app_state: AppState) -> None:
        respx.get(SAMPLE_URL).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        result = await search_page_handle(SAMPLE_URL, "xyzzy_nonexistent", app_state)
        assert result["matches"] == ""
        assert result["outline"] == ""
        assert result["has_more"] is False
        assert result["next_offset"] is None

    @respx.mock
    async def test_search_pagination(self, app_state: AppState) -> None:
        respx.get(SAMPLE_URL).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        result = await search_page_handle(SAMPLE_URL, "stream", app_state, max_results=1)
        match_lines = result["matches"].split("\n")
        assert len(match_lines) == 1
        assert result["has_more"] is True
        assert result["next_offset"] is not None

        result2 = await search_page_handle(
            SAMPLE_URL,
            "stream",
            app_state,
            max_results=100,
            offset=result["next_offset"],
        )
        match_lines2 = result2["matches"].split("\n")
        assert len(match_lines2) > 0
        first_lines = {line.split(":")[0] for line in match_lines}
        second_lines = {line.split(":")[0] for line in match_lines2}
        assert first_lines.isdisjoint(second_lines)

    @respx.mock
    async def test_search_output_contains_all_fields(self, app_state: AppState) -> None:
        respx.get(SAMPLE_URL).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        result = await search_page_handle(SAMPLE_URL, "streaming", app_state)
        assert set(result.keys()) == {
            "url",
            "query",
            "outline",
            "matches",
            "total_lines",
            "has_more",
            "next_offset",
            "content_hash",
            "cached",
            "cached_at",
        }

    async def test_search_url_not_allowed_raises(self, app_state: AppState) -> None:
        evil_url = "https://evil.example.com/docs.md"
        with pytest.raises(ProContextError) as exc_info:
            await search_page_handle(evil_url, "test", app_state)
        assert exc_info.value.code == ErrorCode.URL_NOT_ALLOWED

    @respx.mock
    async def test_search_small_outline_preserves_full_context(self, app_state: AppState) -> None:
        """Small outlines should not be trimmed to the match range."""
        respx.get(SAMPLE_URL).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        result = await search_page_handle(SAMPLE_URL, ".astream()", app_state)
        assert result["matches"] != ""
        outline = result["outline"]
        assert "# Streaming" in outline
