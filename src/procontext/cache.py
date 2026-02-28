"""SQLite documentation cache with stale-while-revalidate.

All cache operations catch ``aiosqlite.Error`` internally and degrade
gracefully: read failures return ``None`` (treated as cache miss by callers),
write failures are logged and ignored (fetched content is still returned).
Infrastructure errors never cross the Cache class boundary.

Note on coding guideline #8 ("Never swallow errors in library code"): That
guideline targets public API surfaces where swallowing errors steals the
decision from the consumer. Cache is an internal infrastructure component —
the design decision (per 02-technical-spec §6.3) is that cache failures must
never prevent the agent from receiving a response. Errors are still logged
with ``exc_info=True`` so they remain observable via stderr.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import aiosqlite
import structlog

from procontext.models.cache import PageCacheEntry, TocCacheEntry

log = structlog.get_logger()

_CREATE_TOC_TABLE = """
CREATE TABLE IF NOT EXISTS toc_cache (
    library_id         TEXT PRIMARY KEY,
    llms_txt_url       TEXT NOT NULL,
    content            TEXT NOT NULL,
    discovered_domains TEXT NOT NULL DEFAULT '',
    fetched_at         TEXT NOT NULL,
    expires_at         TEXT NOT NULL
)
"""

_CREATE_PAGE_TABLE = """
CREATE TABLE IF NOT EXISTS page_cache (
    url_hash           TEXT PRIMARY KEY,
    url                TEXT NOT NULL UNIQUE,
    content            TEXT NOT NULL,
    headings           TEXT NOT NULL DEFAULT '',
    discovered_domains TEXT NOT NULL DEFAULT '',
    fetched_at         TEXT NOT NULL,
    expires_at         TEXT NOT NULL
)
"""

_CREATE_TOC_INDEX = "CREATE INDEX IF NOT EXISTS idx_toc_expires ON toc_cache(expires_at)"
_CREATE_PAGE_INDEX = "CREATE INDEX IF NOT EXISTS idx_page_expires ON page_cache(expires_at)"

_CREATE_METADATA_TABLE = """
CREATE TABLE IF NOT EXISTS server_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""


class Cache:
    """SQLite-backed documentation cache implementing CacheProtocol."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def init_db(self) -> None:
        """Create tables and set WAL mode. Called once at startup."""
        await self._db.execute("PRAGMA journal_mode = WAL")
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._db.execute(_CREATE_TOC_TABLE)
        await self._db.execute(_CREATE_PAGE_TABLE)
        await self._db.execute(_CREATE_TOC_INDEX)
        await self._db.execute(_CREATE_PAGE_INDEX)
        await self._db.execute(_CREATE_METADATA_TABLE)
        await self._db.commit()

    # ------------------------------------------------------------------
    # ToC cache
    # ------------------------------------------------------------------

    async def get_toc(self, library_id: str) -> TocCacheEntry | None:
        """Read a ToC entry. Returns ``None`` on cache miss or read failure."""
        try:
            cursor = await self._db.execute(
                "SELECT library_id, llms_txt_url, content, discovered_domains, "
                "fetched_at, expires_at FROM toc_cache WHERE library_id = ?",
                (library_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None

            fetched_at = datetime.fromisoformat(row[4])
            expires_at = datetime.fromisoformat(row[5])
            stale = datetime.now(UTC) > expires_at

            return TocCacheEntry(
                library_id=row[0],
                llms_txt_url=row[1],
                content=row[2],
                discovered_domains=frozenset(row[3].split()),
                fetched_at=fetched_at,
                expires_at=expires_at,
                stale=stale,
            )
        except aiosqlite.Error:
            log.warning("cache_read_error", key=f"toc:{library_id}", exc_info=True)
            return None

    async def set_toc(
        self,
        library_id: str,
        llms_txt_url: str,
        content: str,
        ttl_hours: int,
        *,
        discovered_domains: frozenset[str] = frozenset(),
    ) -> None:
        """Write a ToC entry. Non-fatal on failure."""
        try:
            now = datetime.now(UTC)
            expires_at = now + timedelta(hours=ttl_hours)
            await self._db.execute(
                "INSERT OR REPLACE INTO toc_cache "
                "(library_id, llms_txt_url, content, discovered_domains, fetched_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    library_id,
                    llms_txt_url,
                    content,
                    " ".join(sorted(discovered_domains)),
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            await self._db.commit()
        except aiosqlite.Error:
            log.warning("cache_write_error", key=f"toc:{library_id}", exc_info=True)

    # ------------------------------------------------------------------
    # Page cache
    # ------------------------------------------------------------------

    async def get_page(self, url_hash: str) -> PageCacheEntry | None:
        """Read a page entry. Returns ``None`` on cache miss or read failure."""
        try:
            cursor = await self._db.execute(
                "SELECT url_hash, url, content, headings, discovered_domains, "
                "fetched_at, expires_at FROM page_cache WHERE url_hash = ?",
                (url_hash,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None

            fetched_at = datetime.fromisoformat(row[5])
            expires_at = datetime.fromisoformat(row[6])
            stale = datetime.now(UTC) > expires_at

            return PageCacheEntry(
                url_hash=row[0],
                url=row[1],
                content=row[2],
                headings=row[3],
                discovered_domains=frozenset(row[4].split()),
                fetched_at=fetched_at,
                expires_at=expires_at,
                stale=stale,
            )
        except aiosqlite.Error:
            log.warning("cache_read_error", key=f"page:{url_hash}", exc_info=True)
            return None

    async def set_page(
        self,
        url: str,
        url_hash: str,
        content: str,
        headings: str,
        ttl_hours: int,
        *,
        discovered_domains: frozenset[str] = frozenset(),
    ) -> None:
        """Write a page entry. Non-fatal on failure."""
        try:
            now = datetime.now(UTC)
            expires_at = now + timedelta(hours=ttl_hours)
            await self._db.execute(
                "INSERT OR REPLACE INTO page_cache "
                "(url_hash, url, content, headings, discovered_domains, fetched_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    url_hash,
                    url,
                    content,
                    headings,
                    " ".join(sorted(discovered_domains)),
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            await self._db.commit()
        except aiosqlite.Error:
            log.warning("cache_write_error", key=f"page:{url_hash}", exc_info=True)

    # ------------------------------------------------------------------
    # Allowlist restoration
    # ------------------------------------------------------------------

    async def load_discovered_domains(
        self, *, include_toc: bool, include_pages: bool
    ) -> frozenset[str]:
        """Collect all discovered domains from cached entries.

        Used at startup to restore the in-memory allowlist from the previous
        session. Non-fatal on database failure — returns empty frozenset.
        """
        if not include_toc and not include_pages:
            return frozenset()
        try:
            domains: set[str] = set()
            if include_toc:
                cursor = await self._db.execute(
                    "SELECT discovered_domains FROM toc_cache WHERE discovered_domains != ''"
                )
                for row in await cursor.fetchall():
                    domains.update(row[0].split())
            if include_pages:
                cursor = await self._db.execute(
                    "SELECT discovered_domains FROM page_cache WHERE discovered_domains != ''"
                )
                for row in await cursor.fetchall():
                    domains.update(row[0].split())
            return frozenset(domains)
        except aiosqlite.Error:
            log.warning("cache_load_discovered_domains_error", exc_info=True)
            return frozenset()

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    async def cleanup_if_due(self, interval_hours: int) -> None:
        """Run cleanup only if interval_hours have elapsed since the last run.

        Reads and writes ``last_cleanup_at`` from the ``server_metadata`` table.
        Falls through to run cleanup if the metadata row is missing or unreadable.
        Non-fatal on failure.
        """
        try:
            cursor = await self._db.execute(
                "SELECT value FROM server_metadata WHERE key = 'last_cleanup_at'"
            )
            row = await cursor.fetchone()
            if row is not None:
                last_run = datetime.fromisoformat(row[0])
                if datetime.now(UTC) - last_run < timedelta(hours=interval_hours):
                    log.debug("cache_cleanup_skipped", reason="not_due")
                    return
        except aiosqlite.Error:
            log.warning("cache_metadata_read_error", exc_info=True)

        await self.cleanup_expired()

        try:
            await self._db.execute(
                "INSERT OR REPLACE INTO server_metadata (key, value) VALUES ('last_cleanup_at', ?)",
                (datetime.now(UTC).isoformat(),),
            )
            await self._db.commit()
        except aiosqlite.Error:
            log.warning("cache_metadata_write_error", exc_info=True)

    async def cleanup_expired(self) -> None:
        """Delete entries expired more than 7 days ago. Non-fatal on failure."""
        try:
            cutoff = (datetime.now(UTC) - timedelta(days=7)).isoformat()

            cursor = await self._db.execute("DELETE FROM toc_cache WHERE expires_at < ?", (cutoff,))
            toc_deleted = cursor.rowcount

            cursor = await self._db.execute(
                "DELETE FROM page_cache WHERE expires_at < ?", (cutoff,)
            )
            page_deleted = cursor.rowcount

            await self._db.commit()
            log.info(
                "cache_cleanup_complete",
                toc_deleted=toc_deleted,
                page_deleted=page_deleted,
            )
        except aiosqlite.Error:
            log.warning("cache_cleanup_error", exc_info=True)
