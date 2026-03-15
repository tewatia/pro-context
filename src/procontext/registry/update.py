"""Remote registry update and setup download logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Literal

import httpx
import structlog

from procontext.models.registry import RegistryEntry, RegistryIndexes
from procontext.registry.local import _sha256_prefixed

if TYPE_CHECKING:
    from pathlib import Path

    from procontext.state import AppState

log = structlog.get_logger()

REGISTRY_SUCCESS_INTERVAL_SECONDS = 24 * 60 * 60
REGISTRY_INITIAL_BACKOFF_SECONDS = 60
REGISTRY_MAX_BACKOFF_SECONDS = 60 * 60
REGISTRY_MAX_TRANSIENT_BACKOFF_ATTEMPTS = 8

RegistryUpdateOutcome = Literal["success", "transient_failure", "semantic_failure"]


@dataclass
class _NewRegistryData:
    """Validated registry download ready to be applied or persisted."""

    registry_bytes: bytes
    version: str
    checksum: str
    entries: list[RegistryEntry]


_REGISTRY_TIMEOUT = httpx.Timeout(300.0, connect=5.0)


async def _download_registry_if_newer(
    http_client: httpx.AsyncClient,
    *,
    metadata_url: str,
    current_version: str | None,
    metadata_timeout: float | httpx.Timeout = _REGISTRY_TIMEOUT,
    registry_timeout: float | httpx.Timeout = _REGISTRY_TIMEOUT,
) -> _NewRegistryData | RegistryUpdateOutcome:
    """Fetch registry metadata and download the full payload if the version changed."""
    metadata_response = await _safe_get(http_client, metadata_url, timeout=metadata_timeout)
    if metadata_response is None:
        return "transient_failure"

    if not metadata_response.is_success:
        return _classify_http_failure(
            url=metadata_url,
            status_code=metadata_response.status_code,
            context="metadata",
        )

    try:
        metadata = metadata_response.json()
        remote_version = metadata["version"]
        download_url = metadata["download_url"]
        expected_checksum = metadata["checksum"]
        if not isinstance(remote_version, str) or not remote_version:
            raise ValueError("'version' must be a non-empty string")
        if not isinstance(download_url, str) or not download_url:
            raise ValueError("'download_url' must be a non-empty string")
        if not isinstance(expected_checksum, str) or not expected_checksum.startswith("sha256:"):
            raise ValueError("'checksum' must be in 'sha256:<hex>' format")
    except Exception:
        log.warning("registry_update_semantic_failure", reason="invalid_metadata", exc_info=True)
        return "semantic_failure"

    if remote_version == current_version:
        log.info("registry_up_to_date", version=remote_version)
        return "success"

    registry_response = await _safe_get(http_client, download_url, timeout=registry_timeout)
    if registry_response is None:
        return "transient_failure"

    if not registry_response.is_success:
        return _classify_http_failure(
            url=download_url,
            status_code=registry_response.status_code,
            context="registry_download",
        )

    actual_checksum = _sha256_prefixed(registry_response.content)
    if actual_checksum != expected_checksum:
        log.warning(
            "registry_checksum_mismatch",
            expected=expected_checksum,
            actual=actual_checksum,
        )
        return "semantic_failure"

    try:
        raw_entries = registry_response.json()
        new_entries = [RegistryEntry(**entry) for entry in raw_entries]
    except Exception:
        log.warning(
            "registry_update_semantic_failure",
            reason="invalid_registry_schema",
            exc_info=True,
        )
        return "semantic_failure"

    return _NewRegistryData(
        registry_bytes=registry_response.content,
        version=remote_version,
        checksum=expected_checksum,
        entries=new_entries,
    )


async def check_for_registry_update(
    state: AppState,
    *,
    build_indexes_fn: Callable[[list[RegistryEntry]], RegistryIndexes],
    build_allowlist_fn: Callable[..., frozenset[str]],
    save_registry_to_disk_fn: Callable[..., None],
    write_last_checked_at_fn: Callable[[Path], None],
    metadata_timeout: float | httpx.Timeout = _REGISTRY_TIMEOUT,
    registry_timeout: float | httpx.Timeout = _REGISTRY_TIMEOUT,
) -> RegistryUpdateOutcome:
    """Check remote metadata and apply a registry update when available."""
    if state.http_client is None:
        return "semantic_failure"

    result = await _download_registry_if_newer(
        state.http_client,
        metadata_url=state.settings.registry.metadata_url,
        current_version=state.registry_version,
        metadata_timeout=metadata_timeout,
        registry_timeout=registry_timeout,
    )

    if isinstance(result, str):
        if result == "success" and state.registry_state_path is not None:
            write_last_checked_at_fn(state.registry_state_path)
        return result

    new_indexes = build_indexes_fn(result.entries)
    new_allowlist = build_allowlist_fn(
        result.entries,
        extra_domains=state.settings.fetcher.extra_allowed_domains,
    )

    state.indexes, state.allowlist, state.registry_version = (
        new_indexes,
        new_allowlist,
        result.version,
    )

    if state.registry_path is not None and state.registry_state_path is not None:
        try:
            save_registry_to_disk_fn(
                registry_bytes=result.registry_bytes,
                version=result.version,
                checksum=result.checksum,
                registry_path=state.registry_path,
                state_path=state.registry_state_path,
            )
        except Exception as exc:
            log.warning(
                "registry_persist_failed",
                version=result.version,
                error=str(exc),
                exc_info=True,
            )

    log.info("registry_updated", version=result.version, entries=len(result.entries))
    return "success"


async def fetch_registry_for_setup(
    *,
    http_client: httpx.AsyncClient,
    metadata_url: str,
    registry_path: Path,
    registry_state_path: Path,
    save_registry_to_disk_fn: Callable[..., None],
) -> bool:
    """Fetch and persist the registry for initial bootstrap."""
    result = await _download_registry_if_newer(
        http_client,
        metadata_url=metadata_url,
        current_version=None,
    )

    if isinstance(result, str):
        return result == "success"

    try:
        save_registry_to_disk_fn(
            registry_bytes=result.registry_bytes,
            version=result.version,
            checksum=result.checksum,
            registry_path=registry_path,
            state_path=registry_state_path,
        )
    except Exception:
        log.warning("registry_setup_persist_failed", exc_info=True)
        return False

    log.info("registry_setup_complete", version=result.version, entries=len(result.entries))
    return True


async def _safe_get(
    http_client: httpx.AsyncClient,
    url: str,
    *,
    timeout: float | httpx.Timeout,
) -> httpx.Response | None:
    try:
        return await http_client.get(url, timeout=timeout)
    except httpx.HTTPError as exc:
        log.warning(
            "registry_update_transient_failure",
            reason="network_error",
            url=url,
            error=str(exc),
        )
        return None


def _classify_http_failure(*, url: str, status_code: int, context: str) -> RegistryUpdateOutcome:
    if status_code >= 500 or status_code in {408, 429}:
        log.warning(
            "registry_update_transient_failure",
            reason="http_status",
            context=context,
            url=url,
            status_code=status_code,
        )
        return "transient_failure"

    log.warning(
        "registry_update_semantic_failure",
        reason="http_status",
        context=context,
        url=url,
        status_code=status_code,
    )
    return "semantic_failure"
