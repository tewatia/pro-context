"""Local registry loading and in-memory index construction."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

import structlog

from procontext.models.registry import RegistryEntry, RegistryIndexes

if TYPE_CHECKING:
    from pathlib import Path

log = structlog.get_logger()


def load_registry(
    local_registry_path: Path | None = None,
    local_state_path: Path | None = None,
) -> tuple[list[RegistryEntry], str] | None:
    """Load registry entries from the local registry pair."""
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
    """Build in-memory indexes from a list of registry entries."""
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


def _sha256_prefixed(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()
