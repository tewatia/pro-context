"""Library registry public API: local loading, persistence, and update checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from procontext.fetcher import build_allowlist

from . import storage as registry_storage
from . import update as registry_update
from .local import build_indexes, load_registry
from .storage import registry_check_is_due, save_registry_to_disk
from .update import (
    REGISTRY_INITIAL_BACKOFF_SECONDS,
    REGISTRY_MAX_BACKOFF_SECONDS,
    REGISTRY_MAX_TRANSIENT_BACKOFF_ATTEMPTS,
    REGISTRY_SUCCESS_INTERVAL_SECONDS,
    RegistryUpdateOutcome,
)

if TYPE_CHECKING:
    from pathlib import Path

    from procontext.state import AppState

_DEFAULT_TIMEOUT = httpx.Timeout(300.0, connect=5.0)

__all__ = [
    "REGISTRY_INITIAL_BACKOFF_SECONDS",
    "REGISTRY_MAX_BACKOFF_SECONDS",
    "REGISTRY_MAX_TRANSIENT_BACKOFF_ATTEMPTS",
    "REGISTRY_SUCCESS_INTERVAL_SECONDS",
    "RegistryUpdateOutcome",
    "build_indexes",
    "check_for_registry_update",
    "fetch_registry_for_setup",
    "load_registry",
    "registry_check_is_due",
    "save_registry_to_disk",
]


async def check_for_registry_update(
    state: AppState,
    *,
    metadata_timeout: float | httpx.Timeout = _DEFAULT_TIMEOUT,
    registry_timeout: float | httpx.Timeout = _DEFAULT_TIMEOUT,
) -> RegistryUpdateOutcome:
    """Check remote metadata and apply a registry update when available."""
    return await registry_update.check_for_registry_update(
        state,
        build_indexes_fn=build_indexes,
        build_allowlist_fn=build_allowlist,
        save_registry_to_disk_fn=save_registry_to_disk,
        write_last_checked_at_fn=registry_storage.write_last_checked_at,
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
    return await registry_update.fetch_registry_for_setup(
        http_client=http_client,
        metadata_url=metadata_url,
        registry_path=registry_path,
        registry_state_path=registry_state_path,
        save_registry_to_disk_fn=save_registry_to_disk,
    )
