"""Protocol interfaces for swappable components.

Tool handlers and AppState reference these protocols, not the concrete
implementations. This allows:
- Tests to use lightweight in-memory implementations
- Future backends (e.g. Redis cache) to be swapped without changing tool code
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from procontext.models.cache import PageCacheEntry, TocCacheEntry


class CacheProtocol(Protocol):
    """Interface for the documentation cache backend."""

    async def get_toc(self, library_id: str) -> TocCacheEntry | None: ...

    async def set_toc(
        self,
        library_id: str,
        llms_txt_url: str,
        content: str,
        ttl_hours: int,
        *,
        discovered_domains: frozenset[str] = frozenset(),
    ) -> None: ...

    async def get_page(self, url_hash: str) -> PageCacheEntry | None: ...

    async def set_page(
        self,
        url: str,
        url_hash: str,
        content: str,
        headings: str,
        ttl_hours: int,
        *,
        discovered_domains: frozenset[str] = frozenset(),
    ) -> None: ...

    async def load_discovered_domains(
        self, *, include_toc: bool, include_pages: bool
    ) -> frozenset[str]: ...

    async def cleanup_if_due(self, interval_hours: int) -> None: ...

    async def cleanup_expired(self) -> None: ...


class FetcherProtocol(Protocol):
    """Interface for the HTTP documentation fetcher."""

    async def fetch(self, url: str, allowlist: frozenset[str]) -> str: ...
