"""Library registry public API: local loading, persistence, and update checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from procontext.fetcher import build_allowlist
from procontext.registry.local import build_indexes as _build_indexes
from procontext.registry.local import load_registry as _load_registry
from procontext.registry.storage import _fsync_directory as _fsync_directory_impl
from procontext.registry.storage import registry_check_is_due as _registry_check_is_due
from procontext.registry.storage import save_registry_to_disk as _save_registry_to_disk
from procontext.registry.storage import write_last_checked_at as _write_last_checked_at_impl
from procontext.registry.update import (
    REGISTRY_INITIAL_BACKOFF_SECONDS,
    REGISTRY_MAX_BACKOFF_SECONDS,
    REGISTRY_MAX_TRANSIENT_BACKOFF_ATTEMPTS,
    REGISTRY_SUCCESS_INTERVAL_SECONDS,
    RegistryUpdateOutcome,
    check_for_registry_update as _check_for_registry_update,
    fetch_registry_for_setup as _fetch_registry_for_setup,
)

if TYPE_CHECKING:
    from pathlib import Path

    from procontext.models.registry import RegistryEntry, RegistryIndexes
    from procontext.state import AppState


def load_registry(
    local_registry_path: Path | None = None,
    local_state_path: Path | None = None,
) -> tuple[list[RegistryEntry], str] | None:
    """Load registry entries from the local registry pair."""
    return _load_registry(local_registry_path, local_state_path)


def build_indexes(entries: list[RegistryEntry]) -> RegistryIndexes:
    """Build in-memory indexes from a list of registry entries."""
    return _build_indexes(entries)


def save_registry_to_disk(
    *,
    registry_bytes: bytes,
    version: str,
    checksum: str,
    registry_path: Path,
    state_path: Path,
) -> None:
    """Persist the local registry pair with atomic replace semantics."""
    _save_registry_to_disk(
        registry_bytes=registry_bytes,
        version=version,
        checksum=checksum,
        registry_path=registry_path,
        state_path=state_path,
    )


def registry_check_is_due(state_path: Path | None, poll_interval_hours: float) -> bool:
    """Return True if poll_interval_hours have elapsed since the last metadata check."""
    return _registry_check_is_due(state_path, poll_interval_hours)


def _write_last_checked_at(state_path: Path) -> None:
    """Update last_checked_at in registry-state.json without touching other fields."""
    _write_last_checked_at_impl(state_path)


def _fsync_directory(path: Path) -> None:
    """Flush a directory entry update to disk where the platform supports it."""
    _fsync_directory_impl(path)


async def check_for_registry_update(
    state: AppState,
    *,
    metadata_timeout: float | httpx.Timeout = httpx.Timeout(300.0, connect=5.0),
    registry_timeout: float | httpx.Timeout = httpx.Timeout(300.0, connect=5.0),
) -> RegistryUpdateOutcome:
    """Check remote metadata and apply a registry update when available."""
    return await _check_for_registry_update(
        state,
        build_indexes_fn=build_indexes,
        build_allowlist_fn=build_allowlist,
        save_registry_to_disk_fn=save_registry_to_disk,
        write_last_checked_at_fn=_write_last_checked_at,
        metadata_timeout=metadata_timeout,
        registry_timeout=registry_timeout,
    )


async def fetch_registry_for_setup(
    *,
    http_client: httpx.AsyncClient,
    metadata_url: str,
    registry_path: Path,
    registry_state_path: Path,
) -> bool:
    """Fetch and persist the registry for initial bootstrap."""
    return await _fetch_registry_for_setup(
        http_client=http_client,
        metadata_url=metadata_url,
        registry_path=registry_path,
        registry_state_path=registry_state_path,
        save_registry_to_disk_fn=save_registry_to_disk,
    )
