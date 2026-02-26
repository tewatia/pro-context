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

        # Manually expire the cached entry
        from datetime import UTC, datetime, timedelta

        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        assert app_state.cache is not None
        await app_state.cache._db.execute(
            "UPDATE toc_cache SET expires_at = ? WHERE library_id = ?",
            (past, "langchain"),
        )
        await app_state.cache._db.commit()

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
