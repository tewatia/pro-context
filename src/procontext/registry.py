"""Library registry: loading, index building, and background update checks."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

import httpx
import structlog

from procontext.fetcher import build_allowlist
from procontext.models.registry import RegistryEntry, RegistryIndexes

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


def load_registry(
    local_registry_path: Path | None = None,
    local_state_path: Path | None = None,
) -> tuple[list[RegistryEntry], str] | None:
    """Load registry entries from the local registry pair.

    Returns (entries, version) if the local registry is found and valid,
    or None if no local registry exists. Run 'procontext setup' to initialise.
    """
    return _load_local_registry_pair(local_registry_path, local_state_path)


def _load_local_registry_pair(
    local_registry_path: Path | None,
    local_state_path: Path | None,
) -> tuple[list[RegistryEntry], str] | None:
    """Load the local registry pair if both files are present and valid."""
    if local_registry_path is None or local_state_path is None:
        return None

    if not local_registry_path.is_file() or not local_state_path.is_file():
        log.debug(
            "registry_local_pair_missing",
            reason="missing_files",
            path_registry=str(local_registry_path),
            path_state=str(local_state_path),
        )
        return None

    try:
        registry_bytes = local_registry_path.read_bytes()
        raw_entries = json.loads(registry_bytes.decode("utf-8"))
        entries = [RegistryEntry(**entry) for entry in raw_entries]

        state_data = json.loads(local_state_path.read_text(encoding="utf-8"))
        version = state_data["version"]
        expected_checksum = state_data["checksum"]
        if not isinstance(version, str) or not version:
            raise ValueError("registry-state.json 'version' must be a non-empty string")
        if not isinstance(expected_checksum, str) or not expected_checksum.startswith("sha256:"):
            raise ValueError("registry-state.json 'checksum' must be 'sha256:<hex>'")

        actual_checksum = _sha256_prefixed(registry_bytes)
        if actual_checksum != expected_checksum:
            log.warning(
                "registry_local_pair_invalid",
                reason="checksum_mismatch",
                path_registry=str(local_registry_path),
                path_state=str(local_state_path),
            )
            return None

        log.info(
            "registry_loaded",
            source="disk",
            entries=len(entries),
            version=version,
            path=str(local_registry_path),
        )
        return entries, version
    except Exception:
        log.warning(
            "registry_local_pair_invalid",
            reason="invalid_content",
            path_registry=str(local_registry_path),
            path_state=str(local_state_path),
            exc_info=True,
        )
        return None


def build_indexes(entries: list[RegistryEntry]) -> RegistryIndexes:
    """Build in-memory indexes from a list of registry entries.

    Single pass over entries, populates three data structures for
    the resolution algorithm (see resolver.py).
    """
    by_package: dict[str, str] = {}
    by_id: dict[str, RegistryEntry] = {}
    by_alias: dict[str, str] = {}
    fuzzy_corpus: list[tuple[str, str]] = []

    for entry in entries:
        by_id[entry.id] = entry
        fuzzy_corpus.append((entry.id, entry.id))

        for pkg in entry.packages.pypi + entry.packages.npm:
            by_package[pkg.lower()] = entry.id
            fuzzy_corpus.append((pkg.lower(), entry.id))

        for alias in entry.aliases:
            by_alias[alias.lower()] = entry.id
            fuzzy_corpus.append((alias.lower(), entry.id))

    return RegistryIndexes(
        by_package=by_package,
        by_id=by_id,
        by_alias=by_alias,
        fuzzy_corpus=fuzzy_corpus,
    )


def save_registry_to_disk(
    *,
    registry_bytes: bytes,
    version: str,
    checksum: str,
    registry_path: Path,
    state_path: Path,
) -> None:
    """Persist the local registry pair with atomic replace semantics."""
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")
    state_payload = {
        "version": version,
        "checksum": checksum,
        "updated_at": now,
        "last_checked_at": now,
    }
    state_bytes = json.dumps(state_payload).encode("utf-8")

    registry_tmp = registry_path.with_suffix(registry_path.suffix + ".tmp")
    state_tmp = state_path.with_suffix(state_path.suffix + ".tmp")

    try:
        _write_bytes_fsync(registry_tmp, registry_bytes)
        _write_bytes_fsync(state_tmp, state_bytes)

        os.replace(registry_tmp, registry_path)
        os.replace(state_tmp, state_path)
        _fsync_directory(registry_path.parent)
    finally:
        for tmp_path in (registry_tmp, state_tmp):
            with suppress(OSError):
                tmp_path.unlink(missing_ok=True)


def registry_check_is_due(state_path: Path | None, poll_interval_hours: float) -> bool:
    """Return True if poll_interval_hours have elapsed since the last metadata check.

    Falls through to True when state_path is None, the state file is missing,
    unreadable, or does not yet contain a last_checked_at timestamp (e.g.
    written by an older version).
    """
    if state_path is None:
        return True
    try:
        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        last_checked_raw = state_data.get("last_checked_at")
        if last_checked_raw is None:
            return True
        last_checked = datetime.fromisoformat(last_checked_raw)
        return datetime.now(tz=UTC) - last_checked >= timedelta(hours=poll_interval_hours)
    except Exception:
        return True


def _write_last_checked_at(state_path: Path) -> None:
    """Update last_checked_at in registry-state.json without touching other fields.

    Non-fatal: failures are logged at debug level and silently ignored.
    """
    try:
        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        state_data["last_checked_at"] = datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")
        state_bytes = json.dumps(state_data).encode("utf-8")
        state_tmp = state_path.with_suffix(state_path.suffix + ".tmp")
        try:
            _write_bytes_fsync(state_tmp, state_bytes)
            os.replace(state_tmp, state_path)
        finally:
            with suppress(OSError):
                state_tmp.unlink(missing_ok=True)
    except Exception:
        log.debug("registry_state_last_checked_at_update_failed", exc_info=True)


_REGISTRY_TIMEOUT = httpx.Timeout(300.0, connect=5.0)


async def _download_registry_if_newer(
    http_client: httpx.AsyncClient,
    *,
    metadata_url: str,
    current_version: str | None,
    metadata_timeout: float | httpx.Timeout = _REGISTRY_TIMEOUT,
    registry_timeout: float | httpx.Timeout = _REGISTRY_TIMEOUT,
) -> _NewRegistryData | RegistryUpdateOutcome:
    """Fetch registry metadata and download the full payload if the version changed.

    Returns _NewRegistryData when a new registry was fetched and validated, or a
    RegistryUpdateOutcome string when no download was needed or an error occurred.
    """
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
            _write_last_checked_at(state.registry_state_path)
        return result

    new_indexes = build_indexes(result.entries)
    new_allowlist = build_allowlist(
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
            save_registry_to_disk(
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
) -> bool:
    """Fetch and persist the registry for initial bootstrap.

    Returns True when the registry was successfully downloaded and saved to disk.
    """
    result = await _download_registry_if_newer(
        http_client,
        metadata_url=metadata_url,
        current_version=None,
    )

    if isinstance(result, str):
        return result == "success"

    try:
        save_registry_to_disk(
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


def _sha256_prefixed(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _write_bytes_fsync(path: Path, data: bytes) -> None:
    with path.open("wb") as file_obj:
        file_obj.write(data)
        file_obj.flush()
        os.fsync(file_obj.fileno())


def _fsync_directory(path: Path) -> None:
    if sys.platform == "win32":
        return  # Windows does not support fsync on directory handles
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
