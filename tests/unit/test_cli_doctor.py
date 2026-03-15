"""Unit tests for the doctor command's health check functions."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import patch

import aiosqlite
import pytest

from procontext.cache import Cache
from procontext.cli.cmd_doctor import (
    check_cache,
    check_data_dir,
    check_network,
    check_registry,
    run_doctor,
)
from procontext.cli.doctor.cache_check import expected_schema
from procontext.cli.doctor.models import CheckResult
from procontext.cli.doctor.output import format_result
from procontext.config import Settings

if TYPE_CHECKING:
    from pathlib import Path

    from procontext.models.registry import RegistryEntry


# ---------------------------------------------------------------------------
# CheckResult & formatting
# ---------------------------------------------------------------------------


class TestCheckResult:
    def test_ok_result(self) -> None:
        r = CheckResult("Test", "ok", "all good")
        assert r.status == "ok"
        assert r.fixed is False

    def test_fail_result(self) -> None:
        r = CheckResult("Test", "fail", "broken", fix_hint="fix it")
        assert r.status == "fail"
        assert r.fix_hint == "fix it"

    def test_warn_result(self) -> None:
        r = CheckResult("Test", "warn", "not ideal")
        assert r.status == "warn"


class TestFormatResult:
    def test_ok_with_detail(self) -> None:
        r = CheckResult("Registry", "ok", "100 libraries")
        line = format_result(r)
        assert "ok" in line
        assert "100 libraries" in line

    def test_fail_with_hint(self) -> None:
        r = CheckResult("Registry", "fail", "not found", fix_hint="run setup")
        line = format_result(r)
        assert "FAIL" in line
        assert "not found" in line
        assert "Fix: run setup" in line

    def test_fixed(self) -> None:
        r = CheckResult("Cache", "ok", "recreated", fixed=True)
        line = format_result(r)
        assert "FIXED" in line
        assert "recreated" in line

    def test_warn(self) -> None:
        r = CheckResult("Cache", "warn", "will be created")
        line = format_result(r)
        assert "WARN" in line


# ---------------------------------------------------------------------------
# Check: Data directory
# ---------------------------------------------------------------------------


class TestCheckDataDir:
    async def test_exists_and_writable(self, tmp_path: Path) -> None:
        registry_dir = tmp_path / "registry"
        registry_dir.mkdir()
        settings = Settings(data_dir=str(tmp_path))
        result = await check_data_dir(settings)
        assert result.status == "ok"

    async def test_missing_reports_fail(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent"
        settings = Settings(data_dir=str(missing))
        result = await check_data_dir(settings)
        assert result.status == "fail"
        assert "does not exist" in result.detail

    async def test_missing_fix_creates(self, tmp_path: Path) -> None:
        missing = tmp_path / "new_dir"
        settings = Settings(data_dir=str(missing))
        result = await check_data_dir(settings, fix=True)
        assert result.fixed is True
        assert missing.exists()
        assert (missing / "registry").exists()

    @pytest.mark.skipif(
        os.name == "nt" or (hasattr(os, "getuid") and os.getuid() == 0),
        reason="Permission checks don't apply on Windows or as root.",
    )
    async def test_not_writable_reports_chmod(self, tmp_path: Path) -> None:
        readonly = tmp_path / "readonly"
        readonly.mkdir()
        (readonly / "registry").mkdir()
        readonly.chmod(0o444)
        try:
            settings = Settings(data_dir=str(readonly))
            result = await check_data_dir(settings)
            assert result.status == "fail"
            assert "chmod" in result.fix_hint
        finally:
            readonly.chmod(0o755)

    async def test_registry_subdir_missing_warns(self, tmp_path: Path) -> None:
        settings = Settings(data_dir=str(tmp_path))
        # tmp_path exists but has no registry/ subdir
        result = await check_data_dir(settings)
        assert result.status == "warn"
        assert "registry" in result.detail.lower()

    async def test_registry_subdir_missing_fix_creates(self, tmp_path: Path) -> None:
        settings = Settings(data_dir=str(tmp_path))
        result = await check_data_dir(settings, fix=True)
        assert result.fixed is True
        assert (tmp_path / "registry").exists()


# ---------------------------------------------------------------------------
# Check: Registry
# ---------------------------------------------------------------------------


class TestCheckRegistry:
    async def test_registry_valid(self, sample_entries: list[RegistryEntry]) -> None:
        with patch(
            "procontext.cli.cmd_doctor.load_registry",
            return_value=(sample_entries, "v2026-01-01"),
        ):
            result = await check_registry(Settings())
        assert result.status == "ok"
        assert "2" in result.detail
        assert "v2026-01-01" in result.detail

    async def test_registry_missing_reports_fix_hint(self, tmp_path: Path) -> None:
        settings = Settings(data_dir=str(tmp_path))
        with patch("procontext.cli.cmd_doctor.load_registry", return_value=None):
            result = await check_registry(settings)
        assert result.status == "fail"
        assert "procontext setup" in result.fix_hint

    async def test_registry_missing_fix_runs_setup(self) -> None:
        with (
            patch("procontext.cli.cmd_doctor.load_registry", side_effect=[None, ([1, 2], "v1")]),
            patch(
                "procontext.cli.cmd_setup.attempt_registry_setup",
                return_value=True,
            ) as mock_setup,
        ):
            result = await check_registry(Settings(), fix=True)
        assert result.fixed is True
        mock_setup.assert_called_once()

    async def test_registry_fix_download_fails(self) -> None:
        with (
            patch("procontext.cli.cmd_doctor.load_registry", return_value=None),
            patch(
                "procontext.cli.cmd_setup.attempt_registry_setup",
                return_value=False,
            ),
        ):
            result = await check_registry(Settings(), fix=True)
        assert result.status == "fail"
        assert "failed" in result.detail.lower()


# ---------------------------------------------------------------------------
# Check: Cache database
# ---------------------------------------------------------------------------


class TestExpectedSchema:
    async def test_returns_both_tables(self) -> None:
        schema = await expected_schema()
        assert "page_cache" in schema
        assert "server_metadata" in schema

    async def test_page_cache_has_expected_columns(self) -> None:
        schema = await expected_schema()
        col_names = list(schema["page_cache"])
        assert "url_hash" in col_names
        assert "url" in col_names
        assert "content" in col_names
        assert "outline" in col_names
        assert "fetched_at" in col_names
        assert "expires_at" in col_names
        assert "last_checked_at" in col_names


class TestCheckCache:
    async def test_db_valid_schema(self, tmp_path: Path) -> None:
        db_path = tmp_path / "cache.db"
        async with aiosqlite.connect(str(db_path)) as db:
            cache = Cache(db)
            await cache.init_db()
        settings = Settings(cache={"db_path": str(db_path)})  # type: ignore[arg-type]
        result = await check_cache(settings)
        assert result.status == "ok"
        assert "schema valid" in result.detail

    async def test_db_not_yet_created_warns(self, tmp_path: Path) -> None:
        db_path = tmp_path / "nonexistent.db"
        settings = Settings(cache={"db_path": str(db_path)})  # type: ignore[arg-type]
        result = await check_cache(settings)
        assert result.status == "warn"
        assert "will be created" in result.detail

    async def test_db_corrupt(self, tmp_path: Path) -> None:
        db_path = tmp_path / "corrupt.db"
        db_path.write_text("this is not a database")
        settings = Settings(cache={"db_path": str(db_path)})  # type: ignore[arg-type]
        result = await check_cache(settings)
        assert result.status == "fail"
        assert "corrupt" in result.detail.lower()

    async def test_db_corrupt_fix_suggests_recreate(self, tmp_path: Path) -> None:
        db_path = tmp_path / "corrupt.db"
        db_path.write_text("this is not a database")
        settings = Settings(cache={"db_path": str(db_path)})  # type: ignore[arg-type]
        result = await check_cache(settings, fix=True)
        assert result.status == "fail"
        assert result.fixed is False
        assert "destructive data loss" in result.detail
        assert "procontext db recreate" in result.fix_hint
        assert db_path.read_text() == "this is not a database"

    async def test_db_missing_table(self, tmp_path: Path) -> None:
        db_path = tmp_path / "partial.db"
        async with aiosqlite.connect(str(db_path)) as db:
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute(
                "CREATE TABLE server_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            await db.commit()
        settings = Settings(cache={"db_path": str(db_path)})  # type: ignore[arg-type]
        result = await check_cache(settings)
        assert result.status == "fail"
        assert "Missing table" in result.detail

    async def test_db_schema_mismatch_missing_column(self, tmp_path: Path) -> None:
        db_path = tmp_path / "old.db"
        async with aiosqlite.connect(str(db_path)) as db:
            await db.execute("PRAGMA journal_mode = WAL")
            # Old schema: missing 'outline' and 'discovered_domains' columns
            await db.execute("""
                CREATE TABLE page_cache (
                    url_hash TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    content TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            """)
            await db.execute(
                "CREATE TABLE server_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            await db.commit()
        settings = Settings(cache={"db_path": str(db_path)})  # type: ignore[arg-type]
        result = await check_cache(settings)
        assert result.status == "fail"
        assert "missing columns" in result.detail.lower()
        assert "outline" in result.detail

    async def test_db_schema_mismatch_fix_migrates_in_place(self, tmp_path: Path) -> None:
        db_path = tmp_path / "old.db"
        url = "https://example.com/docs"
        content = "# Title"
        async with aiosqlite.connect(str(db_path)) as db:
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute(
                """
                CREATE TABLE page_cache (
                    url_hash TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    content TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                "CREATE TABLE server_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            await db.execute(
                """
                INSERT INTO page_cache (url_hash, url, content, fetched_at, expires_at)
                VALUES ('abc', ?, ?, '2026-01-01T00:00:00+00:00', '2026-01-02T00:00:00+00:00')
                """,
                (url, content),
            )
            await db.commit()
        settings = Settings(cache={"db_path": str(db_path)})  # type: ignore[arg-type]
        result = await check_cache(settings, fix=True)
        assert result.fixed is True
        assert "added columns to page_cache" in result.detail
        result2 = await check_cache(settings)
        assert result2.status == "ok"
        async with aiosqlite.connect(str(db_path)) as db:
            cursor = await db.execute(
                "SELECT url, content, outline, discovered_domains, last_checked_at FROM page_cache"
            )
            row = await cursor.fetchone()
        assert row == (url, content, "", "", None)

    async def test_db_missing_table_fix_creates_table(self, tmp_path: Path) -> None:
        db_path = tmp_path / "partial.db"
        async with aiosqlite.connect(str(db_path)) as db:
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute(
                "CREATE TABLE server_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            await db.commit()

        settings = Settings(cache={"db_path": str(db_path)})  # type: ignore[arg-type]
        result = await check_cache(settings, fix=True)
        assert result.fixed is True
        assert "created tables: page_cache" in result.detail
        result2 = await check_cache(settings)
        assert result2.status == "ok"

    async def test_db_non_wal_fix_enables_wal_in_place(self, tmp_path: Path) -> None:
        db_path = tmp_path / "cache.db"
        async with aiosqlite.connect(str(db_path)) as db:
            cache = Cache(db)
            await cache.init_db()
            await db.execute("PRAGMA journal_mode = DELETE")
            await db.execute(
                """
                INSERT INTO page_cache (
                    url_hash, url, content, outline, discovered_domains,
                    fetched_at, expires_at, last_checked_at
                )
                VALUES (
                    'abc', 'https://example.com', '# Title', '1:# Title', '',
                    '2026-01-01T00:00:00+00:00', '2026-01-02T00:00:00+00:00',
                    '2026-01-01T00:00:00+00:00'
                )
                """
            )
            await db.commit()

        settings = Settings(cache={"db_path": str(db_path)})  # type: ignore[arg-type]
        result = await check_cache(settings, fix=True)
        assert result.fixed is True
        assert "enabled WAL mode" in result.detail

        async with aiosqlite.connect(str(db_path)) as db:
            cursor = await db.execute("PRAGMA journal_mode")
            journal_mode = (await cursor.fetchone())[0]
            cursor = await db.execute("SELECT content FROM page_cache WHERE url_hash = 'abc'")
            row = await cursor.fetchone()

        assert journal_mode.lower() == "wal"
        assert row == ("# Title",)

    async def test_parent_dir_missing(self, tmp_path: Path) -> None:
        db_path = tmp_path / "deep" / "nested" / "cache.db"
        settings = Settings(cache={"db_path": str(db_path)})  # type: ignore[arg-type]
        result = await check_cache(settings)
        assert result.status == "fail"
        assert "Parent directory" in result.detail

    async def test_parent_dir_missing_fix_creates(self, tmp_path: Path) -> None:
        db_path = tmp_path / "deep" / "nested" / "cache.db"
        settings = Settings(cache={"db_path": str(db_path)})  # type: ignore[arg-type]
        result = await check_cache(settings, fix=True)
        # After fix, parent exists but DB doesn't yet — that's a warn
        assert result.status == "warn"
        assert db_path.parent.exists()


# ---------------------------------------------------------------------------
# Check: Network
# ---------------------------------------------------------------------------


class TestCheckNetwork:
    async def test_network_reachable(self) -> None:
        with patch("procontext.cli.cmd_doctor.build_http_client") as mock_build:
            mock_client = mock_build.return_value
            mock_response = type("Response", (), {"is_success": True, "status_code": 200})()
            mock_client.head = _async_return(mock_response)
            mock_client.aclose = _async_return(None)
            result = await check_network(Settings())
        assert result.status == "ok"

    async def test_network_unreachable(self) -> None:
        import httpx

        with patch("procontext.cli.cmd_doctor.build_http_client") as mock_build:
            mock_client = mock_build.return_value
            mock_client.head = _async_raise(httpx.ConnectError("connection refused"))
            mock_client.aclose = _async_return(None)
            result = await check_network(Settings())
        assert result.status == "fail"
        assert "connection refused" in result.detail

    async def test_network_http_error(self) -> None:
        with patch("procontext.cli.cmd_doctor.build_http_client") as mock_build:
            mock_client = mock_build.return_value
            mock_response = type("Response", (), {"is_success": False, "status_code": 503})()
            mock_client.head = _async_return(mock_response)
            mock_client.aclose = _async_return(None)
            result = await check_network(Settings())
        assert result.status == "fail"
        assert "503" in result.detail


# ---------------------------------------------------------------------------
# Integration: run_doctor
# ---------------------------------------------------------------------------


class TestRunDoctor:
    async def test_all_pass_exits_0(self) -> None:
        with (
            patch(
                "procontext.cli.cmd_doctor.check_data_dir",
                return_value=CheckResult("Data directory", "ok", "/tmp"),
            ),
            patch(
                "procontext.cli.cmd_doctor.check_registry",
                return_value=CheckResult("Registry", "ok", "2 libraries"),
            ),
            patch(
                "procontext.cli.cmd_doctor.check_cache",
                return_value=CheckResult("Cache", "ok", "schema valid"),
            ),
            patch(
                "procontext.cli.cmd_doctor.check_network",
                return_value=CheckResult("Network", "ok", "reachable"),
            ),
        ):
            await run_doctor(Settings())  # Should not raise

    async def test_any_fail_exits_1(self) -> None:
        with (
            patch(
                "procontext.cli.cmd_doctor.check_data_dir",
                return_value=CheckResult("Data directory", "ok", "/tmp"),
            ),
            patch(
                "procontext.cli.cmd_doctor.check_registry",
                return_value=CheckResult("Registry", "fail", "not found"),
            ),
            patch(
                "procontext.cli.cmd_doctor.check_cache",
                return_value=CheckResult("Cache", "ok", "valid"),
            ),
            patch(
                "procontext.cli.cmd_doctor.check_network",
                return_value=CheckResult("Network", "ok", "reachable"),
            ),
            pytest.raises(SystemExit, match="1"),
        ):
            await run_doctor(Settings())

    async def test_fix_mode_repairs_and_exits_0(self) -> None:
        with (
            patch(
                "procontext.cli.cmd_doctor.check_data_dir",
                return_value=CheckResult("Data directory", "ok", "/tmp"),
            ),
            patch(
                "procontext.cli.cmd_doctor.check_registry",
                return_value=CheckResult("Registry", "ok", "fixed", fixed=True),
            ),
            patch(
                "procontext.cli.cmd_doctor.check_cache",
                return_value=CheckResult("Cache", "ok", "valid"),
            ),
            patch(
                "procontext.cli.cmd_doctor.check_network",
                return_value=CheckResult("Network", "ok", "reachable"),
            ),
        ):
            await run_doctor(Settings(), fix=True)  # Should not raise

    async def test_fix_mode_unfixable_exits_1(self) -> None:
        with (
            patch(
                "procontext.cli.cmd_doctor.check_data_dir",
                return_value=CheckResult("Data directory", "ok", "/tmp"),
            ),
            patch(
                "procontext.cli.cmd_doctor.check_registry",
                return_value=CheckResult("Registry", "fail", "network down"),
            ),
            patch(
                "procontext.cli.cmd_doctor.check_cache",
                return_value=CheckResult("Cache", "ok", "valid"),
            ),
            patch(
                "procontext.cli.cmd_doctor.check_network",
                return_value=CheckResult("Network", "fail", "unreachable"),
            ),
            pytest.raises(SystemExit, match="1"),
        ):
            await run_doctor(Settings(), fix=True)


# -- Helpers --


def _async_return(value: object):  # type: ignore[type-arg]
    """Create an async callable that returns a fixed value."""

    async def _fn(*args: object, **kwargs: object) -> object:
        return value

    return _fn


def _async_raise(exc: BaseException):  # type: ignore[type-arg]
    """Create an async callable that raises an exception."""

    async def _fn(*args: object, **kwargs: object) -> object:
        raise exc

    return _fn
