"""CLI command: procontext doctor — validate system health and optionally repair."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import aiosqlite
import httpx

from procontext.cache import Cache
from procontext.config import registry_paths
from procontext.fetcher import build_http_client
from procontext.registry import load_registry

if TYPE_CHECKING:
    from procontext.config import Settings

_LABEL_WIDTH = 22


@dataclass
class CheckResult:
    """Result of a single health check."""

    name: str
    status: Literal["ok", "warn", "fail"]
    detail: str
    fix_hint: str = ""
    fixed: bool = False


def _format_result(result: CheckResult) -> str:
    """Format a check result for terminal output."""
    dots = "." * (_LABEL_WIDTH - len(result.name))
    if result.fixed:
        status = "FIXED"
    elif result.status == "ok":
        status = "ok"
    elif result.status == "warn":
        status = "WARN"
    else:
        status = "FAIL"
    line = f"  {result.name} {dots} {status}"
    if result.detail:
        if result.status == "fail" and not result.fixed:
            line += f"\n    {result.detail}"
            if result.fix_hint:
                line += f"\n    Fix: {result.fix_hint}"
        else:
            line += f" ({result.detail})"
    return line


# ---------------------------------------------------------------------------
# Check: Data directory
# ---------------------------------------------------------------------------


async def check_data_dir(settings: Settings, *, fix: bool = False) -> CheckResult:
    """Validate data directory exists with proper permissions."""
    data_dir = Path(settings.data_dir)
    registry_dir = data_dir / "registry"

    if not data_dir.exists():
        if fix:
            try:
                data_dir.mkdir(parents=True, exist_ok=True)
                registry_dir.mkdir(exist_ok=True)
                return CheckResult(
                    "Data directory",
                    "ok",
                    str(data_dir),
                    fixed=True,
                )
            except OSError as exc:
                return CheckResult(
                    "Data directory",
                    "fail",
                    f"Failed to create: {exc}",
                )
        return CheckResult(
            "Data directory",
            "fail",
            f"Directory does not exist: {data_dir}",
            fix_hint="run 'procontext doctor --fix' or 'mkdir -p " + str(data_dir) + "'",
        )

    # Check permissions
    if not os.access(data_dir, os.R_OK | os.W_OK | os.X_OK):
        return CheckResult(
            "Data directory",
            "fail",
            f"Insufficient permissions on {data_dir}",
            fix_hint=f"run 'chmod 755 {data_dir}'",
        )

    # Check registry subdirectory
    if not registry_dir.exists():
        if fix:
            try:
                registry_dir.mkdir(parents=True, exist_ok=True)
                return CheckResult(
                    "Data directory",
                    "ok",
                    str(data_dir),
                    fixed=True,
                )
            except OSError as exc:
                return CheckResult(
                    "Data directory",
                    "fail",
                    f"Failed to create registry dir: {exc}",
                )
        return CheckResult(
            "Data directory",
            "warn",
            f"Registry subdirectory missing (will be created by setup): {registry_dir}",
        )

    return CheckResult("Data directory", "ok", str(data_dir))


# ---------------------------------------------------------------------------
# Check: Registry
# ---------------------------------------------------------------------------


async def check_registry(settings: Settings, *, fix: bool = False) -> CheckResult:
    """Validate registry files are present, parseable, and checksum-valid."""
    registry_path, registry_state_path = registry_paths(settings)

    result = load_registry(
        local_registry_path=registry_path,
        local_state_path=registry_state_path,
    )

    if result is not None:
        entries, version = result
        return CheckResult(
            "Registry",
            "ok",
            f"{len(entries):,} libraries, {version}",
        )

    # Registry is missing or invalid
    if fix:
        # Deferred: only needed when --fix is used; avoids pulling in
        # the HTTP client and download logic for a read-only diagnosis.
        from procontext.cli.cmd_setup import attempt_registry_setup

        try:
            success = await attempt_registry_setup(settings)
        except Exception as exc:
            return CheckResult(
                "Registry",
                "fail",
                f"Download failed: {exc}",
            )
        if success:
            # Re-check to get the count
            reloaded = load_registry(
                local_registry_path=registry_path,
                local_state_path=registry_state_path,
            )
            if reloaded:
                entries, version = reloaded
                detail = f"downloaded {len(entries):,} libraries, {version}"
            else:
                detail = "downloaded but failed to reload"
            return CheckResult("Registry", "ok", detail, fixed=True)
        return CheckResult(
            "Registry",
            "fail",
            "Download failed (check network and retry)",
        )

    # Provide specific detail about what's wrong
    if not registry_path.parent.exists():
        detail = f"Registry directory does not exist: {registry_path.parent}"
    elif not registry_path.exists():
        detail = f"Registry file not found: {registry_path}"
    elif not registry_state_path.exists():
        detail = f"Registry state file not found: {registry_state_path}"
    else:
        detail = "Registry files exist but are invalid (corrupt or checksum mismatch)"

    return CheckResult(
        "Registry",
        "fail",
        detail,
        fix_hint="run 'procontext setup' or 'procontext doctor --fix'",
    )


# ---------------------------------------------------------------------------
# Check: Cache database
# ---------------------------------------------------------------------------


async def _expected_schema() -> dict[str, list[tuple[str, str]]]:
    """Build expected schema by running init_db on an in-memory DB.

    This stays in sync with cache.py automatically — no manual schema
    definition to maintain.
    """
    async with aiosqlite.connect(":memory:") as db:
        cache = Cache(db)
        await cache.init_db()
        schema: dict[str, list[tuple[str, str]]] = {}
        for table in ("page_cache", "server_metadata"):
            cursor = await db.execute(f"PRAGMA table_info({table})")  # noqa: S608
            rows = await cursor.fetchall()
            schema[table] = [(row[1], row[2]) for row in rows]
        return schema


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


async def check_cache(settings: Settings, *, fix: bool = False) -> CheckResult:
    """Validate cache database: existence, integrity, and schema."""
    db_path = Path(settings.cache.db_path).expanduser()

    # 1. Check parent directory
    if not db_path.parent.exists():
        if fix:
            try:
                db_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                return CheckResult(
                    "Cache",
                    "fail",
                    f"Failed to create parent directory: {exc}",
                )
        else:
            return CheckResult(
                "Cache",
                "fail",
                f"Parent directory does not exist: {db_path.parent}",
                fix_hint=f"run 'procontext doctor --fix' or 'mkdir -p {db_path.parent}'",
            )

    if db_path.parent.exists() and not os.access(db_path.parent, os.W_OK):
        return CheckResult(
            "Cache",
            "fail",
            f"Parent directory not writable: {db_path.parent}",
            fix_hint=f"run 'chmod 755 {db_path.parent}'",
        )

    # 2. DB doesn't exist yet — that's fine
    if not db_path.exists():
        return CheckResult(
            "Cache",
            "warn",
            f"Database will be created on first run: {db_path}",
        )

    # 3. Try to open and validate
    try:
        async with aiosqlite.connect(str(db_path)) as db:
            # Check WAL mode
            cursor = await db.execute("PRAGMA journal_mode")
            row = await cursor.fetchone()
            journal_mode = row[0] if row else "unknown"

            if journal_mode != "wal":
                if fix:
                    await _recreate_cache(db_path)
                    return CheckResult(
                        "Cache",
                        "ok",
                        f"recreated database at {db_path}",
                        fixed=True,
                    )
                return CheckResult(
                    "Cache",
                    "fail",
                    f"Journal mode is '{journal_mode}', expected 'wal'",
                    fix_hint="run 'procontext doctor --fix' to recreate the database",
                )

            # Check schema
            expected = await _expected_schema()
            for table, expected_cols in expected.items():
                cursor = await db.execute(f"PRAGMA table_info({table})")  # noqa: S608
                rows = await cursor.fetchall()
                if not rows:
                    if fix:
                        await _recreate_cache(db_path)
                        return CheckResult(
                            "Cache",
                            "ok",
                            f"recreated database at {db_path}",
                            fixed=True,
                        )
                    return CheckResult(
                        "Cache",
                        "fail",
                        f"Missing table: {table}",
                        fix_hint="run 'procontext doctor --fix' to recreate the database",
                    )

                actual_cols = [(row[1], row[2]) for row in rows]
                if actual_cols != expected_cols:
                    expected_names = {c[0] for c in expected_cols}
                    actual_names = {c[0] for c in actual_cols}
                    missing = expected_names - actual_names
                    extra = actual_names - expected_names

                    parts = []
                    if missing:
                        parts.append(f"missing columns: {', '.join(sorted(missing))}")
                    if extra:
                        parts.append(f"unexpected columns: {', '.join(sorted(extra))}")
                    if not parts:
                        parts.append("column type or order mismatch")
                    mismatch_detail = f"Table '{table}': {'; '.join(parts)}"

                    if fix:
                        await _recreate_cache(db_path)
                        return CheckResult(
                            "Cache",
                            "ok",
                            f"recreated database at {db_path}",
                            fixed=True,
                        )
                    return CheckResult(
                        "Cache",
                        "fail",
                        f"Schema mismatch — {mismatch_detail}",
                        fix_hint="run 'procontext doctor --fix' to recreate the database",
                    )

    except Exception:
        if fix:
            try:
                await _recreate_cache(db_path)
                return CheckResult(
                    "Cache",
                    "ok",
                    f"recreated database at {db_path}",
                    fixed=True,
                )
            except Exception as recreate_exc:
                return CheckResult(
                    "Cache",
                    "fail",
                    f"Failed to recreate: {recreate_exc}",
                )
        return CheckResult(
            "Cache",
            "fail",
            f"Database is corrupt or unreadable: {db_path}",
            fix_hint="run 'procontext doctor --fix' to recreate the database",
        )

    return CheckResult("Cache", "ok", f"{db_path}, schema valid")


# ---------------------------------------------------------------------------
# Check: Network
# ---------------------------------------------------------------------------


async def check_network(settings: Settings, *, fix: bool = False) -> CheckResult:
    """Check network connectivity to the registry metadata URL."""
    http_client = build_http_client(settings.fetcher)
    try:
        response = await http_client.head(
            settings.registry.metadata_url,
            timeout=httpx.Timeout(10.0, connect=5.0),
        )
        if response.is_success:
            return CheckResult("Network", "ok", "registry reachable")
        return CheckResult(
            "Network",
            "fail",
            f"HTTP {response.status_code} from registry URL",
        )
    except httpx.HTTPError as exc:
        return CheckResult("Network", "fail", str(exc))
    finally:
        await http_client.aclose()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def run_doctor(settings: Settings, *, fix: bool = False) -> None:
    """Run all health checks and print results."""
    header = "ProContext Doctor (--fix)" if fix else "ProContext Doctor"
    print(f"\n{header}\n")  # noqa: T201

    checks = [
        await check_data_dir(settings, fix=fix),
        await check_registry(settings, fix=fix),
        await check_cache(settings, fix=fix),
        await check_network(settings, fix=fix),
    ]

    fail_count = 0
    for result in checks:
        if result.status == "fail" and not result.fixed:
            fail_count += 1
        print(_format_result(result))  # noqa: T201

    print()  # noqa: T201
    if fail_count == 0:
        if any(r.fixed for r in checks):
            print("All issues resolved.")  # noqa: T201
        else:
            print("All checks passed.")  # noqa: T201
    else:
        suffix = "s" if fail_count > 1 else ""
        msg = f"{fail_count} check{suffix} failed."
        if not fix:
            msg += " Run 'procontext doctor --fix' to attempt auto-repair."
        print(msg)  # noqa: T201
        sys.exit(1)
