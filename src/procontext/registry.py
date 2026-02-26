"""Library registry: loading, index building, and background update checks."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING, Literal

import httpx
import structlog

from procontext.fetcher import build_allowlist

if TYPE_CHECKING:
    from pathlib import Path

    from procontext.models.registry import RegistryEntry
    from procontext.state import AppState

log = structlog.get_logger()

REGISTRY_SUCCESS_INTERVAL_SECONDS = 24 * 60 * 60
REGISTRY_INITIAL_BACKOFF_SECONDS = 60
REGISTRY_MAX_BACKOFF_SECONDS = 60 * 60
REGISTRY_MAX_TRANSIENT_BACKOFF_ATTEMPTS = 8

RegistryUpdateOutcome = Literal["success", "transient_failure", "semantic_failure"]


@dataclass
class RegistryIndexes:
    """In-memory indexes built from known-libraries.json at startup.

    Four dicts rebuilt in a single pass (<100ms for 1,000 entries).
    """

    # package name (lowercase) → library ID  e.g. "langchain-openai" → "langchain"
    by_package: dict[str, str] = field(default_factory=dict)

    # library ID → full registry entry
    by_id: dict[str, RegistryEntry] = field(default_factory=dict)

    # alias (lowercase) → library ID  e.g. "lang-chain" → "langchain"
    by_alias: dict[str, str] = field(default_factory=dict)

    # flat list of (term, library_id) pairs for fuzzy matching
    # populated from all IDs + package names + aliases (lowercased)
    fuzzy_corpus: list[tuple[str, str]] = field(default_factory=list)


def load_bundled_registry() -> list[RegistryEntry]:
    """Load the registry snapshot bundled inside the package."""
    from procontext.models.registry import RegistryEntry

    text = files("procontext.data").joinpath("known-libraries.json").read_text(encoding="utf-8")
    raw_entries = json.loads(text)
    return [RegistryEntry(**entry) for entry in raw_entries]


def load_registry(
    local_registry_path: Path | None = None,
    local_state_path: Path | None = None,
) -> tuple[list[RegistryEntry], str]:
    """Load registry entries, preferring a validated local registry pair.

    Returns (entries, version) where version is a string identifier.
    On bundled fallback, version is "unknown".
    """
    local_loaded = _load_local_registry_pair(local_registry_path, local_state_path)
    if local_loaded is not None:
        return local_loaded

    entries = load_bundled_registry()
    log.info("registry_loaded", source="bundled", entries=len(entries), version="unknown")
    return entries, "unknown"


def _load_local_registry_pair(
    local_registry_path: Path | None,
    local_state_path: Path | None,
) -> tuple[list[RegistryEntry], str] | None:
    """Load the local registry pair if both files are present and valid."""
    from procontext.models.registry import RegistryEntry

    if local_registry_path is None or local_state_path is None:
        return None

    if not local_registry_path.is_file() or not local_state_path.is_file():
        log.warning(
            "registry_local_pair_invalid",
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

    state_payload = {
        "version": version,
        "checksum": checksum,
        "updated_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
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


async def check_for_registry_update(state: AppState) -> RegistryUpdateOutcome:
    """Check remote metadata and apply a registry update when available."""
    if state.http_client is None:
        return "semantic_failure"

    metadata_url = state.settings.registry.metadata_url
    metadata_response = await _safe_get(state, metadata_url, timeout=10.0)
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

    if remote_version == state.registry_version:
        log.info("registry_up_to_date", version=remote_version)
        return "success"

    registry_response = await _safe_get(state, download_url, timeout=60.0)
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
        from procontext.models.registry import RegistryEntry

        raw_entries = registry_response.json()
        new_entries = [RegistryEntry(**entry) for entry in raw_entries]
    except Exception:
        log.warning(
            "registry_update_semantic_failure",
            reason="invalid_registry_schema",
            exc_info=True,
        )
        return "semantic_failure"

    new_indexes = build_indexes(new_entries)
    new_allowlist = build_allowlist(new_entries)

    state.indexes, state.allowlist, state.registry_version = (
        new_indexes,
        new_allowlist,
        remote_version,
    )

    if state.registry_path is not None and state.registry_state_path is not None:
        try:
            save_registry_to_disk(
                registry_bytes=registry_response.content,
                version=remote_version,
                checksum=expected_checksum,
                registry_path=state.registry_path,
                state_path=state.registry_state_path,
            )
        except Exception as exc:
            log.warning(
                "registry_persist_failed",
                version=remote_version,
                error=str(exc),
                exc_info=True,
            )

    log.info("registry_updated", version=remote_version, entries=len(new_entries))
    return "success"


async def _safe_get(
    state: AppState,
    url: str,
    *,
    timeout: float,
) -> httpx.Response | None:
    if state.http_client is None:
        return None
    try:
        return await state.http_client.get(url, timeout=timeout)
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
