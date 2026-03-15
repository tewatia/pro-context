"""CLI command: procontext db recreate — destructive cache DB reset."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite

from procontext.cache import Cache

if TYPE_CHECKING:
    from procontext.config import Settings


def _delete_cache_files(db_path: Path) -> None:
    """Delete the cache DB and its WAL/SHM side files."""
    for suffix in ("", "-wal", "-shm"):
        path = db_path.with_name(db_path.name + suffix)
        if path.exists():
            path.unlink()


async def _recreate_cache(db_path: Path) -> None:
    """Delete and recreate the cache database with a fresh schema."""
    _delete_cache_files(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(db_path)) as db:
        cache = Cache(db)
        await cache.init_db()


async def run_db_recreate(settings: Settings) -> None:
    """Delete and recreate the configured cache DB."""
    db_path = Path(settings.cache.db_path).expanduser()
    try:
        await _recreate_cache(db_path)
    except Exception as exc:
        print(  # noqa: T201
            f"Failed to recreate cache database at {db_path}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Recreated cache database at {db_path}")  # noqa: T201
