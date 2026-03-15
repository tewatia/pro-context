"""Application state container.

AppState is created once at server startup (inside the FastMCP lifespan context
manager) and injected into every tool handler via the MCP Context object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    import httpx

    from procontext.config import Settings
    from procontext.models.registry import RegistryIndexes
    from procontext.protocols import CacheProtocol, FetcherProtocol


@dataclass
class AppState:
    """Holds all shared runtime state. Passed to every tool handler."""

    settings: Settings
    indexes: RegistryIndexes
    registry_version: str = ""
    registry_path: Path | None = None
    registry_state_path: Path | None = None
    http_client: httpx.AsyncClient | None = None
    cache: CacheProtocol | None = None
    fetcher: FetcherProtocol | None = None
    allowlist: frozenset[str] = field(default_factory=frozenset)
    _refreshing: set[str] = field(default_factory=set)
