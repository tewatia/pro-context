"""Unit tests for procontext.cache."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import aiosqlite

if TYPE_CHECKING:
    from procontext.cache import Cache

# ---------------------------------------------------------------------------
# ToC cache
# ---------------------------------------------------------------------------


class TestTocCache:
    async def test_set_and_get_fresh(self, cache: Cache) -> None:
        await cache.set_toc(
            library_id="langchain",
            llms_txt_url="https://docs.langchain.com/llms.txt",
            content="# LangChain Docs",
            ttl_hours=24,
        )
        entry = await cache.get_toc("langchain")
        assert entry is not None
        assert entry.library_id == "langchain"
        assert entry.llms_txt_url == "https://docs.langchain.com/llms.txt"
        assert entry.content == "# LangChain Docs"
        assert entry.stale is False
        assert entry.fetched_at is not None
        assert entry.expires_at > datetime.now(UTC)

    async def test_get_nonexistent_returns_none(self, cache: Cache) -> None:
        entry = await cache.get_toc("nonexistent")
        assert entry is None

    async def test_expired_entry_returns_stale(self, cache: Cache) -> None:
        # Write with ttl_hours=0 so it expires immediately
        await cache.set_toc(
            library_id="stale-lib",
            llms_txt_url="https://example.com/llms.txt",
            content="Stale content",
            ttl_hours=0,
        )
        # Manually set expires_at to the past
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        await cache._db.execute(
            "UPDATE toc_cache SET expires_at = ? WHERE library_id = ?",
            (past, "stale-lib"),
        )
        await cache._db.commit()

        entry = await cache.get_toc("stale-lib")
        assert entry is not None
        assert entry.stale is True
        assert entry.content == "Stale content"

    async def test_upsert_overwrites(self, cache: Cache) -> None:
        await cache.set_toc(
            library_id="lib",
            llms_txt_url="https://example.com/llms.txt",
            content="Version 1",
            ttl_hours=24,
        )
        await cache.set_toc(
            library_id="lib",
            llms_txt_url="https://example.com/llms.txt",
            content="Version 2",
            ttl_hours=24,
        )
        entry = await cache.get_toc("lib")
        assert entry is not None
        assert entry.content == "Version 2"

    async def test_discovered_domains_persisted(self, cache: Cache) -> None:
        domains = frozenset({"example.com", "docs.dev"})
        await cache.set_toc(
            library_id="lib",
            llms_txt_url="https://example.com/llms.txt",
            content="Content",
            ttl_hours=24,
            discovered_domains=domains,
        )
        entry = await cache.get_toc("lib")
        assert entry is not None
        assert entry.discovered_domains == domains

    async def test_discovered_domains_defaults_empty(self, cache: Cache) -> None:
        await cache.set_toc(
            library_id="lib",
            llms_txt_url="https://example.com/llms.txt",
            content="Content",
            ttl_hours=24,
        )
        entry = await cache.get_toc("lib")
        assert entry is not None
        assert entry.discovered_domains == frozenset()

    async def test_read_failure_returns_none(self, cache: Cache) -> None:
        """Simulate a database read error — should return None, not raise."""
        original_execute = cache._db.execute

        async def failing_execute(*args, **kwargs):
            raise aiosqlite.OperationalError("disk I/O error")

        cache._db.execute = failing_execute  # type: ignore[assignment]
        entry = await cache.get_toc("langchain")
        assert entry is None
        cache._db.execute = original_execute  # type: ignore[assignment]

    async def test_write_failure_does_not_raise(self, cache: Cache) -> None:
        """Simulate a database write error — should not raise."""
        original_execute = cache._db.execute

        async def failing_execute(*args, **kwargs):
            raise aiosqlite.OperationalError("disk I/O error")

        cache._db.execute = failing_execute  # type: ignore[assignment]
        # This should not raise
        await cache.set_toc(
            library_id="lib",
            llms_txt_url="https://example.com/llms.txt",
            content="Content",
            ttl_hours=24,
        )
        cache._db.execute = original_execute  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Page cache
# ---------------------------------------------------------------------------


class TestPageCache:
    async def test_set_and_get_fresh(self, cache: Cache) -> None:
        await cache.set_page(
            url="https://example.com/docs/page1",
            url_hash="abc123",
            content="# Page 1",
            headings="1: # Page 1",
            ttl_hours=24,
        )
        entry = await cache.get_page("abc123")
        assert entry is not None
        assert entry.url == "https://example.com/docs/page1"
        assert entry.url_hash == "abc123"
        assert entry.content == "# Page 1"
        assert entry.headings == "1: # Page 1"
        assert entry.stale is False

    async def test_get_nonexistent_returns_none(self, cache: Cache) -> None:
        entry = await cache.get_page("nonexistent-hash")
        assert entry is None

    async def test_expired_entry_returns_stale(self, cache: Cache) -> None:
        await cache.set_page(
            url="https://example.com/docs/old",
            url_hash="old-hash",
            content="Old content",
            headings="",
            ttl_hours=0,
        )
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        await cache._db.execute(
            "UPDATE page_cache SET expires_at = ? WHERE url_hash = ?",
            (past, "old-hash"),
        )
        await cache._db.commit()

        entry = await cache.get_page("old-hash")
        assert entry is not None
        assert entry.stale is True

    async def test_discovered_domains_persisted(self, cache: Cache) -> None:
        domains = frozenset({"foo.com", "bar.io"})
        await cache.set_page(
            url="https://example.com/docs/page1",
            url_hash="h1",
            content="# Page",
            headings="1: # Page",
            ttl_hours=24,
            discovered_domains=domains,
        )
        entry = await cache.get_page("h1")
        assert entry is not None
        assert entry.discovered_domains == domains

    async def test_discovered_domains_defaults_empty(self, cache: Cache) -> None:
        await cache.set_page(
            url="https://example.com/docs/page2",
            url_hash="h2",
            content="# Page",
            headings="",
            ttl_hours=24,
        )
        entry = await cache.get_page("h2")
        assert entry is not None
        assert entry.discovered_domains == frozenset()


# ---------------------------------------------------------------------------
# cleanup_expired
# ---------------------------------------------------------------------------


class TestCleanupExpired:
    async def test_cleanup_deletes_old_entries(self, cache: Cache) -> None:
        """Entries expired more than 7 days ago should be deleted."""
        await cache.set_toc(
            library_id="old",
            llms_txt_url="https://example.com/llms.txt",
            content="Old",
            ttl_hours=24,
        )
        # Set expires_at to 8 days in the past
        old_expiry = (datetime.now(UTC) - timedelta(days=8)).isoformat()
        await cache._db.execute(
            "UPDATE toc_cache SET expires_at = ? WHERE library_id = ?",
            (old_expiry, "old"),
        )
        await cache._db.commit()

        await cache.cleanup_expired()

        entry = await cache.get_toc("old")
        assert entry is None

    async def test_cleanup_preserves_recent_expired(self, cache: Cache) -> None:
        """Entries expired within the 7-day grace period should be kept."""
        await cache.set_toc(
            library_id="recent",
            llms_txt_url="https://example.com/llms.txt",
            content="Recent",
            ttl_hours=24,
        )
        # Set expires_at to 2 days in the past (within 7-day grace)
        recent_expiry = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        await cache._db.execute(
            "UPDATE toc_cache SET expires_at = ? WHERE library_id = ?",
            (recent_expiry, "recent"),
        )
        await cache._db.commit()

        await cache.cleanup_expired()

        entry = await cache.get_toc("recent")
        assert entry is not None
        assert entry.content == "Recent"

    async def test_cleanup_failure_does_not_raise(self, cache: Cache) -> None:
        """Simulate a database error during cleanup — should not raise."""
        original_execute = cache._db.execute

        async def failing_execute(*args, **kwargs):
            raise aiosqlite.OperationalError("disk I/O error")

        cache._db.execute = failing_execute  # type: ignore[assignment]
        # Should not raise
        await cache.cleanup_expired()
        cache._db.execute = original_execute  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# load_discovered_domains
# ---------------------------------------------------------------------------


class TestLoadDiscoveredDomains:
    async def test_loads_toc_domains(self, cache: Cache) -> None:
        await cache.set_toc(
            library_id="lib",
            llms_txt_url="https://example.com/llms.txt",
            content="Content",
            ttl_hours=24,
            discovered_domains=frozenset({"example.com", "docs.dev"}),
        )
        result = await cache.load_discovered_domains(include_toc=True, include_pages=False)
        assert "example.com" in result
        assert "docs.dev" in result

    async def test_loads_page_domains(self, cache: Cache) -> None:
        await cache.set_page(
            url="https://example.com/page",
            url_hash="h1",
            content="# Page",
            headings="",
            ttl_hours=24,
            discovered_domains=frozenset({"foo.com"}),
        )
        result = await cache.load_discovered_domains(include_toc=False, include_pages=True)
        assert "foo.com" in result

    async def test_merges_toc_and_page_domains(self, cache: Cache) -> None:
        await cache.set_toc(
            library_id="lib",
            llms_txt_url="https://example.com/llms.txt",
            content="Content",
            ttl_hours=24,
            discovered_domains=frozenset({"toc.com"}),
        )
        await cache.set_page(
            url="https://example.com/page",
            url_hash="h1",
            content="# Page",
            headings="",
            ttl_hours=24,
            discovered_domains=frozenset({"page.io"}),
        )
        result = await cache.load_discovered_domains(include_toc=True, include_pages=True)
        assert "toc.com" in result
        assert "page.io" in result

    async def test_both_false_returns_empty(self, cache: Cache) -> None:
        await cache.set_toc(
            library_id="lib",
            llms_txt_url="https://example.com/llms.txt",
            content="Content",
            ttl_hours=24,
            discovered_domains=frozenset({"example.com"}),
        )
        result = await cache.load_discovered_domains(include_toc=False, include_pages=False)
        assert result == frozenset()

    async def test_skips_entries_with_no_domains(self, cache: Cache) -> None:
        await cache.set_toc(
            library_id="empty",
            llms_txt_url="https://example.com/llms.txt",
            content="Content",
            ttl_hours=24,
        )
        result = await cache.load_discovered_domains(include_toc=True, include_pages=False)
        assert result == frozenset()

    async def test_failure_returns_empty(self, cache: Cache) -> None:
        """Database errors during load should return empty frozenset, not raise."""
        original_execute = cache._db.execute

        async def failing_execute(*args, **kwargs):
            raise aiosqlite.OperationalError("disk I/O error")

        cache._db.execute = failing_execute  # type: ignore[assignment]
        result = await cache.load_discovered_domains(include_toc=True, include_pages=True)
        assert result == frozenset()
        cache._db.execute = original_execute  # type: ignore[assignment]
