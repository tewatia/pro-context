"""Integration test fixtures.

Provides a fully wired AppState with in-memory SQLite, mocked HTTP client,
and all Phase 2 components. Registry-related fixtures come from
tests/conftest.py (sample_entries, indexes).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import aiosqlite
import httpx
import pytest

from procontext.cache import Cache
from procontext.config import Settings
from procontext.fetcher import Fetcher, build_allowlist
from procontext.state import AppState

if TYPE_CHECKING:
    from pathlib import Path

    from procontext.models.registry import RegistryEntry
    from procontext.registry import RegistryIndexes


@pytest.fixture()
def subprocess_env(tmp_path: Path) -> dict[str, str]:
    """Baseline env dict for subprocess-based MCP integration tests.

    Overrides any local procontext.yaml by forcing stdio transport, pointing
    the cache to an isolated tmp directory, and redirecting the registry
    metadata URL to an unlistened port so the first-run fetch fails fast.
    """
    env = os.environ.copy()
    env["PROCONTEXT__SERVER__TRANSPORT"] = "stdio"
    env["PROCONTEXT__CACHE__DB_PATH"] = str(tmp_path / "cache.db")
    env["PROCONTEXT__REGISTRY__METADATA_URL"] = "http://127.0.0.1:1/registry_metadata.json"
    return env


@pytest.fixture()
async def app_state(indexes: RegistryIndexes, sample_entries: list[RegistryEntry]) -> AppState:
    """Full AppState wired for Phase 2 integration tests."""
    async with aiosqlite.connect(":memory:") as db:
        cache = Cache(db)
        await cache.init_db()

        async with httpx.AsyncClient() as client:
            fetcher = Fetcher(client)
            allowlist = build_allowlist(sample_entries)

            state = AppState(
                settings=Settings(),
                indexes=indexes,
                registry_version="test",
                http_client=client,
                cache=cache,
                fetcher=fetcher,
                allowlist=allowlist,
            )
            yield state
