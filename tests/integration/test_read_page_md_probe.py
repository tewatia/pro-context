"""Integration tests for read_page URL probing behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from procontext.errors import ProContextError
from procontext.tools.read_page import handle as read_page_handle
from tests.integration.tool_test_support import SAMPLE_PAGE, SAMPLE_URL

if TYPE_CHECKING:
    from procontext.state import AppState


class TestReadPageMdProbe:
    """Tests for read_page .md probing behavior."""

    @respx.mock
    async def test_non_md_url_fetches_md_variant(self, app_state: AppState) -> None:
        """A URL without .md suffix should transparently fetch url+.md."""
        base_url = "https://python.langchain.com/docs/concepts/streaming"
        md_url = base_url + ".md"
        respx.get(md_url).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        result = await read_page_handle(base_url, 1, 500, app_state)

        assert result["url"] == base_url
        assert result["cached"] is False
        assert "# Streaming" in result["content"]
        assert respx.calls.call_count == 1
        assert str(respx.calls[0].request.url) == md_url

    @respx.mock
    async def test_non_md_url_cached_under_original_url(self, app_state: AppState) -> None:
        """Content fetched via .md probing is cached under the original URL."""
        base_url = "https://python.langchain.com/docs/concepts/streaming"
        md_url = base_url + ".md"
        respx.get(md_url).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        await read_page_handle(base_url, 1, 500, app_state)
        result = await read_page_handle(base_url, 1, 500, app_state)

        assert result["cached"] is True
        assert respx.calls.call_count == 1

    @respx.mock
    async def test_non_md_url_404_falls_back_to_original(self, app_state: AppState) -> None:
        """If the .md variant returns 404, the original URL is fetched as fallback."""
        base_url = "https://python.langchain.com/docs/concepts/streaming"
        md_url = base_url + ".md"
        respx.get(md_url).mock(return_value=httpx.Response(404))
        respx.get(base_url).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        result = await read_page_handle(base_url, 1, 500, app_state)

        assert result["cached"] is False
        assert "# Streaming" in result["content"]
        assert respx.calls.call_count == 2
        assert str(respx.calls[0].request.url) == md_url
        assert str(respx.calls[1].request.url) == base_url

    @respx.mock
    async def test_url_with_extension_not_probed(self, app_state: AppState) -> None:
        """A URL with any file extension is fetched as-is — no .md probe attempted."""
        urls = [
            SAMPLE_URL,
            "https://python.langchain.com/llms.txt",
            "https://python.langchain.com/docs/index.html",
        ]
        for url in urls:
            respx.get(url).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        for url in urls:
            result = await read_page_handle(url, 1, 500, app_state)
            assert result["cached"] is False

        assert respx.calls.call_count == 3

    @respx.mock
    async def test_version_segment_url_is_probed(self, app_state: AppState) -> None:
        """A URL whose last segment looks like a version should still be probed with .md."""
        base_url = "https://python.langchain.com/docs/v1.2"
        md_url = base_url + ".md"
        respx.get(md_url).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        result = await read_page_handle(base_url, 1, 500, app_state)

        assert result["cached"] is False
        assert respx.calls.call_count == 1
        assert str(respx.calls[0].request.url) == md_url

    @respx.mock
    async def test_fragment_url_md_probe_correct_path(self, app_state: AppState) -> None:
        """Fragments must not end up inside the .md extension."""
        base_url = "https://python.langchain.com/docs/concepts/streaming#overview"
        expected_request_url = "https://python.langchain.com/docs/concepts/streaming.md"
        respx.get(expected_request_url).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        result = await read_page_handle(base_url, 1, 500, app_state)

        assert result["cached"] is False
        assert respx.calls.call_count == 1
        assert str(respx.calls[0].request.url) == expected_request_url

    @respx.mock
    async def test_html_md_probe_returned_as_is(self, app_state: AppState) -> None:
        """HTML 200 from the probe is returned as-is without fallback."""
        base_url = "https://python.langchain.com/docs/concepts/streaming"
        md_url = base_url + ".md"
        html_body = "<!DOCTYPE html><html><head></head><body>Not markdown</body></html>"
        respx.get(md_url).mock(return_value=httpx.Response(200, text=html_body))

        result = await read_page_handle(base_url, 1, 500, app_state)

        assert result["cached"] is False
        assert html_body in result["content"]
        assert respx.calls.call_count == 1

    @respx.mock
    async def test_query_string_url_not_probed(self, app_state: AppState) -> None:
        """A URL with query parameters is fetched as-is."""
        url = "https://python.langchain.com/docs/concepts/streaming?v=latest"
        respx.get(url).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        result = await read_page_handle(url, 1, 500, app_state)

        assert result["cached"] is False
        assert respx.calls.call_count == 1
        assert str(respx.calls[0].request.url) == url

    @respx.mock
    async def test_trailing_slash_url_not_probed(self, app_state: AppState) -> None:
        """A URL with a trailing slash is fetched as-is."""
        url = "https://python.langchain.com/docs/concepts/"
        respx.get(url).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        result = await read_page_handle(url, 1, 500, app_state)

        assert result["cached"] is False
        assert respx.calls.call_count == 1
        assert str(respx.calls[0].request.url) == url

    @respx.mock
    async def test_500_on_probe_falls_back_to_original(self, app_state: AppState) -> None:
        """A 500 response from the .md probe triggers fallback to the original URL."""
        base_url = "https://python.langchain.com/docs/concepts/streaming"
        md_url = base_url + ".md"
        respx.get(md_url).mock(return_value=httpx.Response(500))
        respx.get(base_url).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        result = await read_page_handle(base_url, 1, 500, app_state)

        assert result["cached"] is False
        assert "# Streaming" in result["content"]
        assert respx.calls.call_count == 2
        assert str(respx.calls[0].request.url) == md_url
        assert str(respx.calls[1].request.url) == base_url

    @respx.mock
    async def test_timeout_on_probe_falls_back_to_original(self, app_state: AppState) -> None:
        """A timeout on the .md probe triggers fallback to the original URL."""
        base_url = "https://python.langchain.com/docs/concepts/streaming"
        md_url = base_url + ".md"
        respx.get(md_url).mock(side_effect=httpx.TimeoutException("timed out"))
        respx.get(base_url).mock(return_value=httpx.Response(200, text=SAMPLE_PAGE))

        result = await read_page_handle(base_url, 1, 500, app_state)

        assert result["cached"] is False
        assert "# Streaming" in result["content"]
        assert respx.calls.call_count == 2

    @respx.mock
    async def test_probe_and_fallback_both_fail_raises(self, app_state: AppState) -> None:
        """If both the .md probe and the original URL fail, the error is propagated."""
        base_url = "https://python.langchain.com/docs/concepts/streaming"
        md_url = base_url + ".md"
        respx.get(md_url).mock(return_value=httpx.Response(404))
        respx.get(base_url).mock(return_value=httpx.Response(404))

        with pytest.raises(ProContextError):
            await read_page_handle(base_url, 1, 500, app_state)

        assert respx.calls.call_count == 2
