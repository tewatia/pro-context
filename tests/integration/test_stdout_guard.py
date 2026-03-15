"""Integration tests for stdout isolation across tool handlers."""

from __future__ import annotations

import contextlib
import io
from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from procontext.errors import ProContextError
from procontext.tools.read_outline import handle as read_outline_handle
from procontext.tools.read_page import handle as read_page_handle
from procontext.tools.resolve_library import handle as resolve_library_handle
from procontext.tools.search_page import handle as search_page_handle
from tests.integration.tool_test_support import SAMPLE_PAGE, SAMPLE_URL

if TYPE_CHECKING:
    from procontext.state import AppState


def _assert_no_stdout(buffer: io.StringIO, label: str) -> None:
    assert buffer.getvalue() == "", f"stdout polluted by {label}: {buffer.getvalue()!r}"


class TestStdoutGuard:
    """Verify that tool handlers never write to stdout."""

    @respx.mock
    async def test_resolve_library_no_stdout(self, app_state: AppState) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            await resolve_library_handle("langchain", app_state)
            await resolve_library_handle("xyzzy_nonexistent", app_state)
        _assert_no_stdout(buffer, "resolve_library")

    @respx.mock
    async def test_read_page_no_stdout(self, app_state: AppState) -> None:
        respx.get(SAMPLE_URL).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            await read_page_handle(SAMPLE_URL, 1, 500, app_state)
            await read_page_handle(SAMPLE_URL, 1, 100, app_state)
        _assert_no_stdout(buffer, "read_page")

    @respx.mock
    async def test_search_page_no_stdout(self, app_state: AppState) -> None:
        respx.get(SAMPLE_URL).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            await search_page_handle(SAMPLE_URL, "streaming", app_state)
            await search_page_handle(SAMPLE_URL, "xyzzy_nonexistent", app_state)
        _assert_no_stdout(buffer, "search_page")

    @respx.mock
    async def test_read_outline_no_stdout(self, app_state: AppState) -> None:
        respx.get(SAMPLE_URL).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            await read_outline_handle(SAMPLE_URL, 1, 200, app_state)
        _assert_no_stdout(buffer, "read_outline")

    @respx.mock
    async def test_error_paths_no_stdout(self, app_state: AppState) -> None:
        """Error handling paths should also not leak to stdout."""
        respx.get(SAMPLE_URL).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            with pytest.raises(ProContextError):
                await read_page_handle("https://evil.example.com/x.md", 1, 500, app_state)
            with pytest.raises(ProContextError):
                await search_page_handle(SAMPLE_URL, "[invalid", app_state, mode="regex")
        _assert_no_stdout(buffer, "error paths")

    def test_stdout_guard_blocks_write(self) -> None:
        """The runtime guard raises on any write attempt."""
        from procontext.mcp.lifespan import _StdoutGuard

        guard = _StdoutGuard()
        with pytest.raises(RuntimeError, match="reserved for the MCP JSON-RPC"):
            guard.write("oops")

    def test_stdout_guard_flush_is_noop(self) -> None:
        """flush() must not raise."""
        from procontext.mcp.lifespan import _StdoutGuard

        guard = _StdoutGuard()
        guard.flush()
