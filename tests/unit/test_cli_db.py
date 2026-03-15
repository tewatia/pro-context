"""Unit tests for the `procontext db` maintenance commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from procontext.cli.cmd_db import run_db_recreate
from procontext.cli.cmd_doctor import check_cache
from procontext.config import Settings

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class TestRunDbRecreate:
    async def test_recreate_replaces_corrupt_cache(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db_path = tmp_path / "cache.db"
        db_path.write_text("not a database")
        (tmp_path / "cache.db-wal").write_text("wal")
        (tmp_path / "cache.db-shm").write_text("shm")

        settings = Settings(cache={"db_path": str(db_path)})  # type: ignore[arg-type]
        await run_db_recreate(settings)

        captured = capsys.readouterr()
        assert "Recreated cache database" in captured.out

        result = await check_cache(settings)
        assert result.status == "ok"
