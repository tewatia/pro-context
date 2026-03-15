"""Registry persistence and state-file helpers."""

from __future__ import annotations

import json
import os
import sys
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

log = structlog.get_logger()


def save_registry_to_disk(
    *,
    registry_bytes: bytes,
    version: str,
    checksum: str,
    registry_path: Path,
    state_path: Path,
    write_bytes_fsync_fn: Callable[[Path, bytes], None] | None = None,
    fsync_directory_fn: Callable[[Path], None] | None = None,
) -> None:
    """Persist the local registry pair with atomic replace semantics."""
    write_bytes_fsync = write_bytes_fsync_fn or _write_bytes_fsync
    fsync_directory = fsync_directory_fn or _fsync_directory

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")
    state_payload = {
        "version": version,
        "checksum": checksum,
        "updated_at": now,
        "last_checked_at": now,
    }
    state_bytes = json.dumps(state_payload).encode("utf-8")

    registry_tmp = registry_path.with_suffix(registry_path.suffix + ".tmp")
    state_tmp = state_path.with_suffix(state_path.suffix + ".tmp")

    try:
        write_bytes_fsync(registry_tmp, registry_bytes)
        write_bytes_fsync(state_tmp, state_bytes)

        os.replace(registry_tmp, registry_path)
        os.replace(state_tmp, state_path)
        fsync_directory(registry_path.parent)
    finally:
        for tmp_path in (registry_tmp, state_tmp):
            with suppress(OSError):
                tmp_path.unlink(missing_ok=True)


def registry_check_is_due(state_path: Path | None, poll_interval_hours: float) -> bool:
    """Return True if poll_interval_hours have elapsed since the last metadata check."""
    if state_path is None:
        return True
    try:
        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        last_checked_raw = state_data.get("last_checked_at")
        if last_checked_raw is None:
            return True
        last_checked = datetime.fromisoformat(last_checked_raw)
        return datetime.now(tz=UTC) - last_checked >= timedelta(hours=poll_interval_hours)
    except Exception:
        log.debug("registry_check_is_due_parse_failed", path=str(state_path), exc_info=True)
        return True


def write_last_checked_at(
    state_path: Path,
    *,
    write_bytes_fsync_fn: Callable[[Path, bytes], None] | None = None,
) -> None:
    """Update last_checked_at in registry-state.json without touching other fields."""
    write_bytes_fsync = write_bytes_fsync_fn or _write_bytes_fsync
    try:
        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        state_data["last_checked_at"] = datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")
        state_bytes = json.dumps(state_data).encode("utf-8")
        state_tmp = state_path.with_suffix(state_path.suffix + ".tmp")
        try:
            write_bytes_fsync(state_tmp, state_bytes)
            os.replace(state_tmp, state_path)
        finally:
            with suppress(OSError):
                state_tmp.unlink(missing_ok=True)
    except Exception:
        log.debug("registry_state_last_checked_at_update_failed", exc_info=True)


def _write_bytes_fsync(path: Path, data: bytes) -> None:
    with path.open("wb") as file_obj:
        file_obj.write(data)
        file_obj.flush()
        os.fsync(file_obj.fileno())


def _fsync_directory(path: Path) -> None:
    if sys.platform == "win32":
        return
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
