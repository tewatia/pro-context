"""Integration tests for MCP tool handlers.

Tests the full path through each handler: input validation → business logic
→ output serialisation. Uses a real AppState with in-memory fixtures.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from procontext.cache import Cache
from procontext.errors import ErrorCode, ProContextError
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
            "description",
            "languages",
            "llms_txt_url",
            "docs_url",
            "readme_url",
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

        result = await read_page_handle(_SAMPLE_URL, 1, 500, app_state)

        assert result["url"] == _SAMPLE_URL
        assert result["cached"] is False
        assert result["cached_at"] is None
        assert result["stale"] is False
        assert result["total_lines"] == 21
        assert "# Streaming" in result["outline"]
        assert "## Overview" in result["outline"]
        assert "# Streaming" in result["content"]

    @respx.mock
    async def test_cache_hit_returns_cached(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        # First call — cache miss
        await read_page_handle(_SAMPLE_URL, 1, 500, app_state)

        # Second call — cache hit
        result = await read_page_handle(_SAMPLE_URL, 1, 500, app_state)
        assert result["cached"] is True
        assert result["cached_at"] is not None
        assert result["stale"] is False

        # Only one HTTP request was made
        assert respx.calls.call_count == 1

    @respx.mock
    async def test_stale_cache_returns_stale_true(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        # First call to populate cache
        await read_page_handle(_SAMPLE_URL, 1, 500, app_state)

        # Artificially expire the cached entry to simulate stale-while-revalidate.
        # Accesses Cache._db directly because the public API has no way to set a
        # past expiry. This couples the test to the SQLite implementation — acceptable
        # here since Cache's own unit tests cover the backend contract independently.
        from datetime import UTC, datetime, timedelta

        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        assert isinstance(app_state.cache, Cache)
        await app_state.cache._db.execute(  # pyright: ignore[reportPrivateUsage]
            "UPDATE page_cache SET expires_at = ? WHERE url = ?",
            (past, _SAMPLE_URL),
        )
        await app_state.cache._db.commit()  # pyright: ignore[reportPrivateUsage]

        # Second call — stale hit
        result = await read_page_handle(_SAMPLE_URL, 1, 500, app_state)
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
    async def test_outline_always_full_page(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        # Even with a narrow window, outline reflects the full page
        result = await read_page_handle(_SAMPLE_URL, 1, 2, app_state)
        outline = result["outline"]

        # Should contain all headings, not just those in the window
        assert "## Streaming with Chains" in outline

    @respx.mock
    async def test_total_lines_correct(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        result = await read_page_handle(_SAMPLE_URL, 1, 500, app_state)
        actual_lines = len(_SAMPLE_PAGE.splitlines())
        assert result["total_lines"] == actual_lines

    @respx.mock
    async def test_url_not_in_allowlist_raises(self, app_state: AppState) -> None:
        evil_url = "https://evil.example.com/docs.md"
        respx.get(evil_url).mock(return_value=httpx.Response(200, text="# Evil"))

        with pytest.raises(ProContextError) as exc_info:
            await read_page_handle(evil_url, 1, 500, app_state)
        assert exc_info.value.code == ErrorCode.URL_NOT_ALLOWED
        assert exc_info.value.recoverable is False

    @respx.mock
    async def test_404_raises_page_not_found(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(404))

        with pytest.raises(ProContextError) as exc_info:
            await read_page_handle(_SAMPLE_URL, 1, 500, app_state)
        assert exc_info.value.code == ErrorCode.PAGE_NOT_FOUND
        assert exc_info.value.recoverable is False

    @respx.mock
    async def test_network_error_raises_fetch_failed(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(503))

        with pytest.raises(ProContextError) as exc_info:
            await read_page_handle(_SAMPLE_URL, 1, 500, app_state)
        assert exc_info.value.code == ErrorCode.PAGE_FETCH_FAILED
        assert exc_info.value.recoverable is True

    @respx.mock
    async def test_too_many_redirects_raises_redirect_error(self, app_state: AppState) -> None:
        r1 = "https://python.langchain.com/docs/concepts/r1.md"
        r2 = "https://python.langchain.com/docs/concepts/r2.md"
        r3 = "https://python.langchain.com/docs/concepts/r3.md"
        r4 = "https://python.langchain.com/docs/concepts/r4.md"
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(301, headers={"location": r1}))
        respx.get(r1).mock(return_value=httpx.Response(301, headers={"location": r2}))
        respx.get(r2).mock(return_value=httpx.Response(301, headers={"location": r3}))
        respx.get(r3).mock(return_value=httpx.Response(301, headers={"location": r4}))
        respx.get(r4).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        with pytest.raises(ProContextError) as exc_info:
            await read_page_handle(_SAMPLE_URL, 1, 500, app_state)
        assert exc_info.value.code == ErrorCode.TOO_MANY_REDIRECTS
        assert exc_info.value.recoverable is False

    async def test_invalid_url_scheme_raises(self, app_state: AppState) -> None:
        with pytest.raises(ProContextError) as exc_info:
            await read_page_handle("ftp://example.com/docs.md", 1, 500, app_state)
        assert exc_info.value.code == ErrorCode.INVALID_INPUT
        assert exc_info.value.recoverable is False

    async def test_url_too_long_raises(self, app_state: AppState) -> None:
        long_url = "https://example.com/" + "a" * 2040
        with pytest.raises(ProContextError) as exc_info:
            await read_page_handle(long_url, 1, 500, app_state)
        assert exc_info.value.code == ErrorCode.INVALID_INPUT

    @respx.mock
    async def test_output_contains_all_required_fields(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        result = await read_page_handle(_SAMPLE_URL, 1, 500, app_state)
        assert set(result.keys()) == {
            "url",
            "outline",
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
        assert result["outline"] != ""  # Outline still present

    @respx.mock
    async def test_view_outline_omits_content(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        result = await read_page_handle(_SAMPLE_URL, 1, 500, app_state, view="outline")

        assert "content" not in result
        assert "outline" in result
        assert "total_lines" in result
        assert "# Streaming" in result["outline"]

    @respx.mock
    async def test_view_outline_total_lines_correct(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        result = await read_page_handle(_SAMPLE_URL, 1, 500, app_state, view="outline")

        assert result["total_lines"] == len(_SAMPLE_PAGE.splitlines())

    @respx.mock
    async def test_view_full_explicit_returns_content(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        result = await read_page_handle(_SAMPLE_URL, 1, 500, app_state, view="full")

        assert "content" in result
        assert "# Streaming" in result["content"]

    @respx.mock
    async def test_view_default_is_full(self, app_state: AppState) -> None:
        respx.get(_SAMPLE_URL).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        result = await read_page_handle(_SAMPLE_URL, 1, 500, app_state)

        assert "content" in result

    # --- .md URL probing ---

    @respx.mock
    async def test_non_md_url_fetches_md_variant(self, app_state: AppState) -> None:
        """A URL without .md suffix should transparently fetch url+.md."""
        base_url = "https://python.langchain.com/docs/concepts/streaming"
        md_url = base_url + ".md"
        respx.get(md_url).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        result = await read_page_handle(base_url, 1, 500, app_state)

        assert result["url"] == base_url
        assert result["cached"] is False
        assert "# Streaming" in result["content"]
        # Only the .md variant was requested — original URL must not have been called
        assert respx.calls.call_count == 1
        assert str(respx.calls[0].request.url) == md_url

    @respx.mock
    async def test_non_md_url_cached_under_original_url(self, app_state: AppState) -> None:
        """Content fetched via .md probing is cached under the original URL."""
        base_url = "https://python.langchain.com/docs/concepts/streaming"
        md_url = base_url + ".md"
        respx.get(md_url).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        # First call — cache miss, network fetch
        await read_page_handle(base_url, 1, 500, app_state)
        # Second call — should be a cache hit (no additional network call)
        result = await read_page_handle(base_url, 1, 500, app_state)

        assert result["cached"] is True
        assert respx.calls.call_count == 1  # Only one network request total

    @respx.mock
    async def test_non_md_url_404_falls_back_to_original(self, app_state: AppState) -> None:
        """If the .md variant returns 404, the original URL is fetched as fallback."""
        base_url = "https://python.langchain.com/docs/concepts/streaming"
        md_url = base_url + ".md"
        respx.get(md_url).mock(return_value=httpx.Response(404))
        respx.get(base_url).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        result = await read_page_handle(base_url, 1, 500, app_state)

        assert result["cached"] is False
        assert "# Streaming" in result["content"]
        assert respx.calls.call_count == 2
        assert str(respx.calls[0].request.url) == md_url
        assert str(respx.calls[1].request.url) == base_url

    @respx.mock
    async def test_url_with_extension_not_probed(self, app_state: AppState) -> None:
        """A URL with any file extension is fetched as-is — no .md probe attempted."""
        for url in [
            _SAMPLE_URL,  # .md
            "https://python.langchain.com/llms.txt",  # .txt
            "https://python.langchain.com/docs/index.html",  # .html
        ]:
            respx.get(url).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        for url in [
            _SAMPLE_URL,
            "https://python.langchain.com/llms.txt",
            "https://python.langchain.com/docs/index.html",
        ]:
            result = await read_page_handle(url, 1, 500, app_state)
            assert result["cached"] is False

        # Each URL fetched exactly once — no .md probes
        assert respx.calls.call_count == 3

    @respx.mock
    async def test_version_segment_url_is_probed(self, app_state: AppState) -> None:
        """A URL whose last segment looks like a version (e.g. v1.2) should still be
        probed with .md — numeric-only suffixes are not real file extensions."""
        base_url = "https://python.langchain.com/docs/v1.2"
        md_url = base_url + ".md"
        respx.get(md_url).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        result = await read_page_handle(base_url, 1, 500, app_state)

        assert result["cached"] is False
        assert respx.calls.call_count == 1
        assert str(respx.calls[0].request.url) == md_url

    @respx.mock
    async def test_fragment_url_md_probe_correct_path(self, app_state: AppState) -> None:
        """Fragment in URL must not end up inside the .md extension.

        https://example.com/docs/page#section should probe
        https://example.com/docs/page.md (fragment stripped by httpx, never sent to server),
        not https://example.com/docs/page#section.md which would put .md inside the fragment.
        """
        base_url = "https://python.langchain.com/docs/concepts/streaming#overview"
        # httpx strips fragments before sending — the request lands at the path only
        expected_request_url = "https://python.langchain.com/docs/concepts/streaming.md"
        respx.get(expected_request_url).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        result = await read_page_handle(base_url, 1, 500, app_state)

        assert result["cached"] is False
        assert respx.calls.call_count == 1
        # .md is in the path, not inside the fragment
        assert str(respx.calls[0].request.url) == expected_request_url

    @respx.mock
    async def test_html_md_probe_returned_as_is(self, app_state: AppState) -> None:
        """HTML 200 from .md probe is returned as-is — no fallback, since the original
        URL would also return HTML on an SPA (the content is identical either way)."""
        base_url = "https://python.langchain.com/docs/concepts/streaming"
        md_url = base_url + ".md"
        html_body = "<!DOCTYPE html><html><head></head><body>Not markdown</body></html>"
        respx.get(md_url).mock(return_value=httpx.Response(200, text=html_body))

        result = await read_page_handle(base_url, 1, 500, app_state)

        assert result["cached"] is False
        assert html_body in result["content"]
        assert respx.calls.call_count == 1  # Only .md was requested, no fallback

    @respx.mock
    async def test_query_string_url_not_probed(self, app_state: AppState) -> None:
        """A URL with query parameters is fetched as-is — .md probe is skipped.

        Static file servers that serve raw markdown don't use query params,
        so the probe would always 404. Fetch the original URL directly.
        """
        url = "https://python.langchain.com/docs/concepts/streaming?v=latest"
        respx.get(url).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        result = await read_page_handle(url, 1, 500, app_state)

        assert result["cached"] is False
        assert respx.calls.call_count == 1
        assert str(respx.calls[0].request.url) == url

    @respx.mock
    async def test_trailing_slash_url_not_probed(self, app_state: AppState) -> None:
        """A URL with a trailing slash is fetched as-is — appending .md would
        produce an invalid path like /docs/page/.md."""
        url = "https://python.langchain.com/docs/concepts/"
        respx.get(url).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

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
        respx.get(base_url).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

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
        respx.get(base_url).mock(return_value=httpx.Response(200, text=_SAMPLE_PAGE))

        result = await read_page_handle(base_url, 1, 500, app_state)

        assert result["cached"] is False
        assert "# Streaming" in result["content"]
        assert respx.calls.call_count == 2

    @respx.mock
    async def test_probe_and_fallback_both_fail_raises(self, app_state: AppState) -> None:
        """If both the .md probe and the original URL fail, the error is propagated."""
        from procontext.errors import ProContextError

        base_url = "https://python.langchain.com/docs/concepts/streaming"
        md_url = base_url + ".md"
        respx.get(md_url).mock(return_value=httpx.Response(404))
        respx.get(base_url).mock(return_value=httpx.Response(404))

        with pytest.raises(ProContextError):
            await read_page_handle(base_url, 1, 500, app_state)

        assert respx.calls.call_count == 2
