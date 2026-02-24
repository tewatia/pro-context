"""Integration tests for MCP tool handlers.

Tests the full path through each handler: input validation → business logic
→ output serialisation. Uses a real AppState with in-memory fixtures.
"""

from __future__ import annotations

import pytest

from pro_context.errors import ErrorCode, ProContextError
from pro_context.state import AppState
from pro_context.tools.resolve_library import handle


class TestResolveLibraryHandler:
    """Full handler pipeline tests for resolve-library."""

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
