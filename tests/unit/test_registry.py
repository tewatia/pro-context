from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import patch

import httpx

from procontext.config import Settings
from procontext.fetcher import build_allowlist
from procontext.registry import (
    _fsync_directory,
    _write_last_checked_at,
    check_for_registry_update,
    fetch_registry_for_setup,
    load_registry,
    registry_check_is_due,
    save_registry_to_disk,
)
from procontext.state import AppState

if TYPE_CHECKING:
    from pathlib import Path


def _sha256_prefixed(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _build_state(
    *,
    client: httpx.AsyncClient,
    tmp_path: Path,
    indexes,
    sample_entries,
    registry_version: str = "unknown",
) -> AppState:
    settings = Settings(
        cache={"db_path": str(tmp_path / "cache.db")},
        registry={"metadata_url": "https://registry.example/registry_metadata.json"},
    )
    return AppState(
        settings=settings,
        indexes=indexes,
        registry_version=registry_version,
        registry_path=tmp_path / "registry" / "known-libraries.json",
        registry_state_path=tmp_path / "registry" / "registry-state.json",
        http_client=client,
        allowlist=build_allowlist(sample_entries),
    )


def test_load_registry_uses_valid_local_pair(tmp_path: Path) -> None:
    payload = [
        {
            "id": "localonly",
            "name": "LocalOnly",
            "llms_txt_url": "https://docs.localonly.dev/llms.txt",
        }
    ]
    registry_bytes = json.dumps(payload).encode("utf-8")
    checksum = _sha256_prefixed(registry_bytes)

    registry_path = tmp_path / "known-libraries.json"
    state_path = tmp_path / "registry-state.json"
    registry_path.write_bytes(registry_bytes)
    state_path.write_text(
        json.dumps(
            {
                "version": "2026-02-25",
                "checksum": checksum,
                "updated_at": "2026-02-25T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    entries, version = load_registry(registry_path, state_path)

    assert version == "2026-02-25"
    assert [entry.id for entry in entries] == ["localonly"]


def test_load_registry_returns_none_on_checksum_mismatch(tmp_path: Path) -> None:
    payload = [
        {
            "id": "localonly",
            "name": "LocalOnly",
            "llms_txt_url": "https://docs.localonly.dev/llms.txt",
        }
    ]

    registry_path = tmp_path / "known-libraries.json"
    state_path = tmp_path / "registry-state.json"
    registry_path.write_text(json.dumps(payload), encoding="utf-8")
    state_path.write_text(
        json.dumps(
            {
                "version": "2026-02-25",
                "checksum": "sha256:deadbeef",
                "updated_at": "2026-02-25T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    assert load_registry(registry_path, state_path) is None


def test_save_registry_to_disk_writes_registry_pair(tmp_path: Path) -> None:
    payload = [
        {
            "id": "persistedlib",
            "name": "PersistedLib",
            "llms_txt_url": "https://docs.persisted.dev/llms.txt",
        }
    ]
    registry_bytes = json.dumps(payload).encode("utf-8")
    checksum = _sha256_prefixed(registry_bytes)

    registry_path = tmp_path / "registry" / "known-libraries.json"
    state_path = tmp_path / "registry" / "registry-state.json"

    save_registry_to_disk(
        registry_bytes=registry_bytes,
        version="2026-02-26",
        checksum=checksum,
        registry_path=registry_path,
        state_path=state_path,
    )

    assert registry_path.read_bytes() == registry_bytes
    state_data = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_data["version"] == "2026-02-26"
    assert state_data["checksum"] == checksum
    assert "updated_at" in state_data
    assert "last_checked_at" in state_data


async def test_check_for_registry_update_success_updates_state(
    tmp_path: Path,
    indexes,
    sample_entries,
) -> None:
    updated_entries = [
        {
            "id": "newlib",
            "name": "NewLib",
            "llms_txt_url": "https://docs.newlib.dev/llms.txt",
            "docs_url": "https://docs.newlib.dev",
        }
    ]
    registry_bytes = json.dumps(updated_entries).encode("utf-8")
    checksum = _sha256_prefixed(registry_bytes)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("registry_metadata.json"):
            return httpx.Response(
                200,
                json={
                    "version": "2026-02-26",
                    "download_url": "https://registry.example/known-libraries.json",
                    "checksum": checksum,
                },
            )
        if request.url.path.endswith("known-libraries.json"):
            return httpx.Response(200, content=registry_bytes)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        state = _build_state(
            client=client,
            tmp_path=tmp_path,
            indexes=indexes,
            sample_entries=sample_entries,
            registry_version="2026-02-20",
        )
        outcome = await check_for_registry_update(state)

    assert outcome == "success"
    assert state.registry_version == "2026-02-26"
    assert "newlib" in state.indexes.by_id
    assert state.registry_path is not None and state.registry_path.is_file()
    assert state.registry_state_path is not None and state.registry_state_path.is_file()


async def test_check_for_registry_update_transient_on_metadata_5xx(
    tmp_path: Path,
    indexes,
    sample_entries,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        state = _build_state(
            client=client,
            tmp_path=tmp_path,
            indexes=indexes,
            sample_entries=sample_entries,
        )
        outcome = await check_for_registry_update(state)

    assert outcome == "transient_failure"
    assert state.registry_version == "unknown"


async def test_check_for_registry_update_semantic_on_checksum_mismatch(
    tmp_path: Path,
    indexes,
    sample_entries,
) -> None:
    updated_entries = [
        {
            "id": "newlib",
            "name": "NewLib",
            "llms_txt_url": "https://docs.newlib.dev/llms.txt",
        }
    ]
    registry_bytes = json.dumps(updated_entries).encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("registry_metadata.json"):
            return httpx.Response(
                200,
                json={
                    "version": "2026-02-26",
                    "download_url": "https://registry.example/known-libraries.json",
                    "checksum": "sha256:deadbeef",
                },
            )
        if request.url.path.endswith("known-libraries.json"):
            return httpx.Response(200, content=registry_bytes)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        state = _build_state(
            client=client,
            tmp_path=tmp_path,
            indexes=indexes,
            sample_entries=sample_entries,
            registry_version="2026-02-20",
        )
        outcome = await check_for_registry_update(state)

    assert outcome == "semantic_failure"
    assert state.registry_version == "2026-02-20"


class TestRegistryCheckIsDue:
    def test_no_state_file_returns_true(self, tmp_path: Path) -> None:
        assert registry_check_is_due(tmp_path / "missing.json", 24) is True

    def test_no_last_checked_at_field_returns_true(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps({"version": "1", "checksum": "sha256:abc"}), encoding="utf-8"
        )
        assert registry_check_is_due(state_file, 24) is True

    def test_recent_check_returns_false(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "version": "1",
                    "checksum": "sha256:abc",
                    "last_checked_at": datetime.now(UTC).isoformat(),
                }
            ),
            encoding="utf-8",
        )
        assert registry_check_is_due(state_file, 24) is False

    def test_stale_check_returns_true(self, tmp_path: Path) -> None:
        stale = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps({"version": "1", "checksum": "sha256:abc", "last_checked_at": stale}),
            encoding="utf-8",
        )
        assert registry_check_is_due(state_file, 24) is True

    def test_corrupt_state_file_returns_true(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_bytes(b"not valid json")
        assert registry_check_is_due(state_file, 24) is True


class TestFetchRegistryForSetup:
    """Tests for fetch_registry_for_setup.

    fetch_registry_for_setup always passes current_version=None to
    _download_registry_if_newer, so a remote version string can never equal
    None — the download always runs. The defensive `result == "success"` branch
    in the function body is therefore unreachable in normal operation and is not
    tested here.
    """

    async def test_success_downloads_and_persists(self, tmp_path: Path) -> None:
        """Happy path: valid metadata + registry → files written, returns True."""
        entries = [
            {
                "id": "setuplib",
                "name": "SetupLib",
                "llms_txt_url": "https://docs.setuplib.dev/llms.txt",
            }
        ]
        registry_bytes = json.dumps(entries).encode("utf-8")
        checksum = _sha256_prefixed(registry_bytes)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("registry_metadata.json"):
                return httpx.Response(
                    200,
                    json={
                        "version": "2026-03-01",
                        "download_url": "https://registry.example/known-libraries.json",
                        "checksum": checksum,
                    },
                )
            if request.url.path.endswith("known-libraries.json"):
                return httpx.Response(200, content=registry_bytes)
            return httpx.Response(404)

        registry_path = tmp_path / "registry" / "known-libraries.json"
        state_path = tmp_path / "registry" / "registry-state.json"

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await fetch_registry_for_setup(
                http_client=client,
                metadata_url="https://registry.example/registry_metadata.json",
                registry_path=registry_path,
                registry_state_path=state_path,
            )

        assert result is True
        assert registry_path.read_bytes() == registry_bytes
        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        assert state_data["version"] == "2026-03-01"
        assert state_data["checksum"] == checksum

    async def test_transient_failure_returns_false(self, tmp_path: Path) -> None:
        """503 on metadata fetch → transient failure → returns False, no files written."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        registry_path = tmp_path / "registry" / "known-libraries.json"
        state_path = tmp_path / "registry" / "registry-state.json"

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await fetch_registry_for_setup(
                http_client=client,
                metadata_url="https://registry.example/registry_metadata.json",
                registry_path=registry_path,
                registry_state_path=state_path,
            )

        assert result is False
        assert not registry_path.exists()
        assert not state_path.exists()

    async def test_checksum_mismatch_returns_false(self, tmp_path: Path) -> None:
        """Metadata checksum doesn't match registry body → returns False, no files written."""
        entries = [{"id": "lib", "name": "Lib", "llms_txt_url": "https://docs.lib.dev/llms.txt"}]
        registry_bytes = json.dumps(entries).encode("utf-8")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("registry_metadata.json"):
                return httpx.Response(
                    200,
                    json={
                        "version": "2026-03-01",
                        "download_url": "https://registry.example/known-libraries.json",
                        "checksum": "sha256:deadbeef",  # does not match body
                    },
                )
            if request.url.path.endswith("known-libraries.json"):
                return httpx.Response(200, content=registry_bytes)
            return httpx.Response(404)

        registry_path = tmp_path / "registry" / "known-libraries.json"
        state_path = tmp_path / "registry" / "registry-state.json"

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await fetch_registry_for_setup(
                http_client=client,
                metadata_url="https://registry.example/registry_metadata.json",
                registry_path=registry_path,
                registry_state_path=state_path,
            )

        assert result is False
        assert not registry_path.exists()
        assert not state_path.exists()

    async def test_persist_failure_returns_false(self, tmp_path: Path) -> None:
        """Download succeeds but save_registry_to_disk raises → returns False."""
        entries = [{"id": "lib", "name": "Lib", "llms_txt_url": "https://docs.lib.dev/llms.txt"}]
        registry_bytes = json.dumps(entries).encode("utf-8")
        checksum = _sha256_prefixed(registry_bytes)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("registry_metadata.json"):
                return httpx.Response(
                    200,
                    json={
                        "version": "2026-03-01",
                        "download_url": "https://registry.example/known-libraries.json",
                        "checksum": checksum,
                    },
                )
            if request.url.path.endswith("known-libraries.json"):
                return httpx.Response(200, content=registry_bytes)
            return httpx.Response(404)

        registry_path = tmp_path / "registry" / "known-libraries.json"
        state_path = tmp_path / "registry" / "registry-state.json"

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with patch(
                "procontext.registry.save_registry_to_disk",
                side_effect=OSError("disk full"),
            ):
                result = await fetch_registry_for_setup(
                    http_client=client,
                    metadata_url="https://registry.example/registry_metadata.json",
                    registry_path=registry_path,
                    registry_state_path=state_path,
                )

        assert result is False


class TestFsyncDirectoryWindowsGuard:
    """Verify _fsync_directory is a no-op on Windows."""

    def test_noop_on_win32(self, tmp_path: Path) -> None:
        with patch("procontext.registry.sys") as mock_sys:
            mock_sys.platform = "win32"
            # Should return without calling os.open or os.fsync
            _fsync_directory(tmp_path)

    def test_executes_on_non_windows(self, tmp_path: Path) -> None:
        with patch("procontext.registry.sys") as mock_sys:
            mock_sys.platform = "linux"
            # On a real filesystem (macOS/Linux CI), this should succeed
            _fsync_directory(tmp_path)

    def test_save_registry_to_disk_succeeds_on_win32(self, tmp_path: Path) -> None:
        payload = [{"id": "test", "name": "Test", "llms_txt_url": "https://example.com/llms.txt"}]
        registry_bytes = json.dumps(payload).encode("utf-8")
        checksum = _sha256_prefixed(registry_bytes)

        registry_path = tmp_path / "registry" / "known-libraries.json"
        state_path = tmp_path / "registry" / "registry-state.json"

        with patch("procontext.registry.sys") as mock_sys:
            mock_sys.platform = "win32"
            save_registry_to_disk(
                registry_bytes=registry_bytes,
                version="2026-02-26",
                checksum=checksum,
                registry_path=registry_path,
                state_path=state_path,
            )

        assert registry_path.read_bytes() == registry_bytes


# ---------------------------------------------------------------------------
# load_registry edge cases
# ---------------------------------------------------------------------------


def test_load_registry_returns_none_when_both_paths_none() -> None:
    assert load_registry(None, None) is None


def test_load_registry_returns_none_when_files_missing(tmp_path: Path) -> None:
    assert load_registry(tmp_path / "missing.json", tmp_path / "also-missing.json") is None


def test_load_registry_returns_none_on_invalid_version_type(tmp_path: Path) -> None:
    """A non-string version (e.g. integer) in registry-state.json → None."""
    payload = [{"id": "lib", "name": "Lib", "llms_txt_url": "https://docs.lib.dev/llms.txt"}]
    registry_bytes = json.dumps(payload).encode("utf-8")
    checksum = _sha256_prefixed(registry_bytes)

    registry_path = tmp_path / "known-libraries.json"
    state_path = tmp_path / "registry-state.json"
    registry_path.write_bytes(registry_bytes)
    state_path.write_text(
        json.dumps({"version": 123, "checksum": checksum}),
        encoding="utf-8",
    )

    assert load_registry(registry_path, state_path) is None


def test_load_registry_returns_none_on_invalid_checksum_format(tmp_path: Path) -> None:
    """A checksum that does not start with 'sha256:' → None."""
    payload = [{"id": "lib", "name": "Lib", "llms_txt_url": "https://docs.lib.dev/llms.txt"}]
    registry_bytes = json.dumps(payload).encode("utf-8")

    registry_path = tmp_path / "known-libraries.json"
    state_path = tmp_path / "registry-state.json"
    registry_path.write_bytes(registry_bytes)
    state_path.write_text(
        json.dumps({"version": "1.0", "checksum": "not-sha256-prefixed"}),
        encoding="utf-8",
    )

    assert load_registry(registry_path, state_path) is None


def test_load_registry_returns_none_on_corrupt_json(tmp_path: Path) -> None:
    """A registry file that is not valid JSON → None."""
    registry_path = tmp_path / "known-libraries.json"
    state_path = tmp_path / "registry-state.json"
    registry_path.write_bytes(b"not valid json {{{")
    state_path.write_text(
        json.dumps({"version": "1.0", "checksum": "sha256:abc"}),
        encoding="utf-8",
    )

    assert load_registry(registry_path, state_path) is None


# ---------------------------------------------------------------------------
# _write_last_checked_at
# ---------------------------------------------------------------------------


class TestWriteLastCheckedAt:
    def test_updates_last_checked_at_and_preserves_other_fields(self, tmp_path: Path) -> None:
        """Updates last_checked_at in-place without touching other state fields."""
        state_path = tmp_path / "registry-state.json"
        original = {
            "version": "2026-02-20",
            "checksum": "sha256:abc",
            "updated_at": "2026-01-01T00:00:00Z",
            "last_checked_at": "2026-01-01T00:00:00Z",
        }
        state_path.write_text(json.dumps(original), encoding="utf-8")

        before = datetime.now(UTC)
        _write_last_checked_at(state_path)
        after = datetime.now(UTC)

        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        assert state_data["version"] == "2026-02-20"
        assert state_data["checksum"] == "sha256:abc"
        assert state_data["updated_at"] == "2026-01-01T00:00:00Z"
        last_checked = datetime.fromisoformat(state_data["last_checked_at"])
        assert before <= last_checked <= after

    def test_nonexistent_file_does_not_raise(self, tmp_path: Path) -> None:
        """A missing state file is silently ignored (non-fatal)."""
        _write_last_checked_at(tmp_path / "nonexistent.json")


# ---------------------------------------------------------------------------
# check_for_registry_update — up-to-date path and 4xx semantic failure
# ---------------------------------------------------------------------------


async def test_check_for_registry_update_up_to_date_writes_last_checked_at(
    tmp_path: Path,
    indexes,
    sample_entries,
) -> None:
    """When remote version equals current, returns 'success' and updates last_checked_at."""
    current_version = "2026-02-20"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "version": current_version,
                "download_url": "https://registry.example/known-libraries.json",
                "checksum": "sha256:abc123",
            },
        )

    # Write a state file for _write_last_checked_at to update
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir(parents=True, exist_ok=True)
    old_checked = "2026-01-01T00:00:00Z"
    (registry_dir / "registry-state.json").write_text(
        json.dumps(
            {
                "version": current_version,
                "checksum": "sha256:abc123",
                "last_checked_at": old_checked,
            }
        ),
        encoding="utf-8",
    )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        state = _build_state(
            client=client,
            tmp_path=tmp_path,
            indexes=indexes,
            sample_entries=sample_entries,
            registry_version=current_version,
        )
        outcome = await check_for_registry_update(state)

    assert outcome == "success"
    assert state.registry_version == current_version  # unchanged

    state_data = json.loads((registry_dir / "registry-state.json").read_text(encoding="utf-8"))
    assert state_data["last_checked_at"] != old_checked  # timestamp was refreshed


async def test_check_for_registry_update_semantic_on_metadata_4xx(
    tmp_path: Path,
    indexes,
    sample_entries,
) -> None:
    """A 4xx response on the metadata URL maps to semantic_failure (not transient)."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        state = _build_state(
            client=client,
            tmp_path=tmp_path,
            indexes=indexes,
            sample_entries=sample_entries,
        )
        outcome = await check_for_registry_update(state)

    assert outcome == "semantic_failure"
    assert state.registry_version == "unknown"  # unchanged
