"""Application state container.

AppState is created once at server startup (inside the FastMCP lifespan context
manager) and injected into every tool handler via the MCP Context object.

Fields are populated progressively across implementation phases:
  Phase 0 — settings only
  Phase 1 — indexes, registry_version
  Phase 2 — http_client, cache, fetcher, allowlist
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

    from pro_context.config import Settings
    from pro_context.protocols import CacheProtocol, FetcherProtocol
    from pro_context.registry import RegistryIndexes


@dataclass
class AppState:
    """Holds all shared runtime state. Passed to every tool handler."""

    # Phase 0
    settings: Settings

    # Phase 1: Registry & Resolution
    indexes: RegistryIndexes
    registry_version: str = ""

    # Phase 2: Fetcher & Cache
    http_client: httpx.AsyncClient | None = None
    cache: CacheProtocol | None = None
    fetcher: FetcherProtocol | None = None
    allowlist: frozenset[str] = field(default_factory=frozenset)
