"""Integration tests for the read_outline tool handler."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from procontext.errors import ErrorCode, ProContextError
from procontext.tools.read_outline import handle as read_outline_handle
from procontext.tools.read_page import handle as read_page_handle
from tests.integration.tool_test_support import SAMPLE_PAGE, SAMPLE_URL

if TYPE_CHECKING:
    from procontext.state import AppState


class TestReadOutlineHandler:
    """Full handler pipeline tests for read_outline."""

    @respx.mock
    async def test_basic_outline(self, app_state: AppState) -> None:
        respx.get(SAMPLE_URL).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        result = await read_outline_handle(SAMPLE_URL, 1, 200, app_state)

        assert result["url"] == SAMPLE_URL
        assert result["total_entries"] > 0
        assert "# Streaming" in result["outline"]
        assert result["cached"] is False

    @respx.mock
    async def test_output_contains_all_fields(self, app_state: AppState) -> None:
        respx.get(SAMPLE_URL).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        result = await read_outline_handle(SAMPLE_URL, 1, 200, app_state)
        assert set(result.keys()) == {
            "url",
            "outline",
            "total_entries",
            "has_more",
            "next_offset",
            "content_hash",
            "cached",
            "cached_at",
            "stale",
        }

    @respx.mock
    async def test_pagination(self, app_state: AppState) -> None:
        respx.get(SAMPLE_URL).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        result = await read_outline_handle(SAMPLE_URL, 1, 2, app_state)
        assert result["outline"].count("\n") <= 1
        assert result["has_more"] is True
        assert result["next_offset"] is not None

        result2 = await read_outline_handle(SAMPLE_URL, result["next_offset"], 2, app_state)
        assert result2["cached"] is True
        assert result2["outline"] != result["outline"]

    @respx.mock
    async def test_offset_beyond_total_entries(self, app_state: AppState) -> None:
        respx.get(SAMPLE_URL).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        result = await read_outline_handle(SAMPLE_URL, 9999, 200, app_state)
        assert result["outline"] == ""
        assert result["has_more"] is False
        assert result["next_offset"] is None
        assert result["total_entries"] > 0

    @respx.mock
    async def test_cache_shared_with_read_page(self, app_state: AppState) -> None:
        """read_page populates cache, read_outline uses it."""
        respx.get(SAMPLE_URL).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        await read_page_handle(SAMPLE_URL, 1, 500, app_state)
        assert respx.calls.call_count == 1

        result = await read_outline_handle(SAMPLE_URL, 1, 200, app_state)
        assert result["cached"] is True
        assert respx.calls.call_count == 1

    async def test_url_not_allowed_raises(self, app_state: AppState) -> None:
        evil_url = "https://evil.example.com/docs.md"
        with pytest.raises(ProContextError) as exc_info:
            await read_outline_handle(evil_url, 1, 200, app_state)
        assert exc_info.value.code == ErrorCode.URL_NOT_ALLOWED

    @respx.mock
    async def test_large_limit_accepted(self, app_state: AppState) -> None:
        respx.get(SAMPLE_URL).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))
        result = await read_outline_handle(SAMPLE_URL, 1, 5000, app_state)
        assert result["url"] == SAMPLE_URL
