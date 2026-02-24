"""Library registry: loading, index building, and background update check.

Loads known-libraries.json from disk or the bundled snapshot, builds
in-memory indexes for fast resolution, and provides the RegistryIndexes
dataclass consumed by the resolver.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib.resources import files
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pathlib import Path

    from pro_context.models.registry import RegistryEntry

log = structlog.get_logger()


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
    from pro_context.models.registry import RegistryEntry

    text = (
        files("pro_context.data")
        .joinpath("known-libraries.json")
        .read_text(encoding="utf-8")
    )
    raw_entries = json.loads(text)
    return [RegistryEntry(**entry) for entry in raw_entries]


def load_registry(local_path: Path | None = None) -> tuple[list[RegistryEntry], str]:
    """Load registry entries, preferring a local file over the bundled snapshot.

    Returns (entries, version) where version is a string identifier.
    The local path is typically ~/.local/share/pro-context/registry/known-libraries.json.
    """
    from pro_context.models.registry import RegistryEntry

    if local_path and local_path.is_file():
        try:
            raw = json.loads(local_path.read_text(encoding="utf-8"))
            entries = [RegistryEntry(**e) for e in raw]
            log.info("registry_loaded", source="disk", entries=len(entries), path=str(local_path))
            # Version from disk registry is determined by registry_metadata.json (Phase 5).
            # For now, use "disk" as a sentinel.
            return entries, "disk"
        except Exception:
            log.warning("registry_disk_load_failed", path=str(local_path), exc_info=True)

    entries = load_bundled_registry()
    log.info("registry_loaded", source="bundled", entries=len(entries))
    return entries, "bundled"


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


# check_for_registry_update() — Phase 5
