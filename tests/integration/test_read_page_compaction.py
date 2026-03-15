"""Integration tests for read_page outline compaction."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import respx

from procontext.tools.read_page import handle as read_page_handle
from tests.integration.tool_test_support import SAMPLE_PAGE, SAMPLE_URL

if TYPE_CHECKING:
    from procontext.state import AppState


class TestReadPageCompaction:
    """Tests for outline compaction in read_page output."""

    @respx.mock
    async def test_small_outline_not_compacted(self, app_state: AppState) -> None:
        """Pages with <=50 outline entries are returned as-is."""
        respx.get(SAMPLE_URL).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        result = await read_page_handle(SAMPLE_URL, 1, 500, app_state)
        assert "[Compacted:" not in result["outline"]
        assert "# Streaming" in result["outline"]

    @respx.mock
    async def test_large_outline_compacted_with_note(self, app_state: AppState) -> None:
        """Pages with >50 outline entries get compacted with a note header."""
        lines = ["# Main Title", ""]
        for index in range(60):
            lines.append(f"### Section {index}")
            lines.append(f"Content for section {index}.")
            lines.append("")
        big_page = "\n".join(lines)
        url = "https://python.langchain.com/docs/big-page.md"
        respx.get(url).mock(return_value=httpx.Response(200, text=big_page))

        result = await read_page_handle(url, 1, 500, app_state)
        outline = result["outline"]
        assert "[Compacted:" in outline
        assert "read_outline" in outline

    @respx.mock
    async def test_irreducible_outline_shows_status_message(self, app_state: AppState) -> None:
        """Pages with >50 H1/H2-only headings show the 'too large' message."""
        lines = []
        for index in range(55):
            lines.append(f"## Section {index}")
            lines.append(f"Content {index}.")
            lines.append("")
        big_page = "\n".join(lines)
        url = "https://python.langchain.com/docs/huge-page.md"
        respx.get(url).mock(return_value=httpx.Response(200, text=big_page))

        result = await read_page_handle(url, 1, 500, app_state)
        outline = result["outline"]
        assert "[Outline too large" in outline
        assert "read_outline" in outline
