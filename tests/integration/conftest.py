"""Integration test fixtures.

Provides a fully wired AppState with in-memory SQLite, mocked HTTP client,
and all Phase 2 components. Registry-related fixtures come from
tests/conftest.py (sample_entries, indexes).
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
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

    from procontext.models.registry import RegistryEntry, RegistryIndexes


def _write_registry(data_dir: "Path", entries: list[dict]) -> None:
    """Write a valid registry pair to <data_dir>/registry/."""
    registry_dir = data_dir / "registry"
    registry_dir.mkdir(parents=True, exist_ok=True)
    registry_bytes = json.dumps(entries).encode("utf-8")
    checksum = "sha256:" + hashlib.sha256(registry_bytes).hexdigest()
    (registry_dir / "known-libraries.json").write_bytes(registry_bytes)
    now = datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")
    (registry_dir / "registry-state.json").write_text(
        json.dumps({
            "version": "test",
            "checksum": checksum,
            "updated_at": "2026-01-01T00:00:00Z",
            "last_checked_at": now,
        }),
        encoding="utf-8",
    )


@pytest.fixture()
def subprocess_env(tmp_path: "Path") -> dict[str, str]:
    """Baseline env dict for subprocess-based MCP integration tests.

    Overrides any local procontext.yaml by forcing stdio transport, pointing
    all data paths to an isolated tmp directory, and seeding a minimal registry.
    """
    _write_registry(tmp_path, [
        {
            "id": "requests",
            "name": "requests",
            "llms_txt_url": "https://docs.python-requests.org/llms.txt",
            "packages": {"pypi": ["requests"]},
        },
        {
            "id": "langchain",
            "name": "LangChain",
            "docs_url": "https://python.langchain.com/docs/",
            "llms_txt_url": "https://python.langchain.com/llms.txt",
            "packages": {"pypi": ["langchain", "langchain-openai", "langchain-core"]},
        },
    ])
    env = os.environ.copy()
    env["PROCONTEXT__SERVER__TRANSPORT"] = "stdio"
    env["PROCONTEXT__DATA_DIR"] = str(tmp_path)
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
