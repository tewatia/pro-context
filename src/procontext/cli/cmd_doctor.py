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


@dataclass(frozen=True)
class ColumnSpec:
    """Schema metadata for a single SQLite column."""

    name: str
    declared_type: str
    not_null: bool
    default: str | None
    primary_key: bool


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


def _cache_recreate_command() -> str:
    """Return the CLI command that force-recreates the cache DB."""
    return "procontext db recreate"


async def _expected_schema() -> dict[str, dict[str, ColumnSpec]]:
    """Build expected schema by running init_db on an in-memory DB.

    This stays in sync with cache.py automatically — no manual schema
    definition to maintain.
    """
    async with aiosqlite.connect(":memory:") as db:
        cache = Cache(db)
        await cache.init_db()
        schema: dict[str, dict[str, ColumnSpec]] = {}
        for table in ("page_cache", "server_metadata"):
            cursor = await db.execute(f"PRAGMA table_info({table})")  # noqa: S608
            rows = await cursor.fetchall()
            schema[table] = {
                row[1]: ColumnSpec(
                    name=row[1],
                    declared_type=row[2],
                    not_null=bool(row[3]),
                    default=row[4],
                    primary_key=bool(row[5]),
                )
                for row in rows
            }
        return schema


async def _load_schema(
    db: aiosqlite.Connection,
    tables: tuple[str, ...] = ("page_cache", "server_metadata"),
) -> dict[str, dict[str, ColumnSpec]]:
    """Load the current on-disk schema for the tracked cache tables."""
    schema: dict[str, dict[str, ColumnSpec]] = {}
    for table in tables:
        cursor = await db.execute(f"PRAGMA table_info({table})")  # noqa: S608
        rows = await cursor.fetchall()
        schema[table] = {
            row[1]: ColumnSpec(
                name=row[1],
                declared_type=row[2],
                not_null=bool(row[3]),
                default=row[4],
                primary_key=bool(row[5]),
            )
            for row in rows
        }
    return schema


def _column_is_compatible(actual: ColumnSpec, expected: ColumnSpec) -> bool:
    """Return True if the existing column definition matches expectations."""
    return (
        actual.declared_type.upper() == expected.declared_type.upper()
        and actual.not_null == expected.not_null
        and actual.default == expected.default
        and actual.primary_key == expected.primary_key
    )


def _column_definition_sql(spec: ColumnSpec) -> str:
    """Build an ALTER TABLE-compatible column definition."""
    parts = [spec.name, spec.declared_type]
    if spec.primary_key:
        parts.append("PRIMARY KEY")
    if spec.not_null:
        parts.append("NOT NULL")
    if spec.default is not None:
        parts.append(f"DEFAULT {spec.default}")
    return " ".join(parts)


def _can_add_column_in_place(spec: ColumnSpec) -> bool:
    """Return True if a missing column can be added without rebuilding the table."""
    if spec.primary_key:
        return False
    if spec.not_null and spec.default is None:
        return False
    return True


def _schema_mismatch_detail(
    actual: dict[str, dict[str, ColumnSpec]],
    expected: dict[str, dict[str, ColumnSpec]],
) -> str | None:
    """Return a human-readable schema mismatch detail, or None if compatible."""
    details: list[str] = []
    for table, expected_cols in expected.items():
        actual_cols = actual[table]
        if not actual_cols:
            details.append(f"Missing table: {table}")
            continue

        missing = [name for name in expected_cols if name not in actual_cols]
        if missing:
            details.append(f"Table '{table}': missing columns: {', '.join(sorted(missing))}")

        incompatible: list[str] = []
        for name, expected_col in expected_cols.items():
            actual_col = actual_cols.get(name)
            if actual_col is None or _column_is_compatible(actual_col, expected_col):
                continue

            parts: list[str] = []
            if actual_col.declared_type.upper() != expected_col.declared_type.upper():
                parts.append(
                    f"type {actual_col.declared_type or '<empty>'} != {expected_col.declared_type}"
                )
            if actual_col.not_null != expected_col.not_null:
                parts.append(
                    f"nullability {'NOT NULL' if actual_col.not_null else 'NULL'} != "
                    f"{'NOT NULL' if expected_col.not_null else 'NULL'}"
                )
            if actual_col.default != expected_col.default:
                parts.append(f"default {actual_col.default!r} != {expected_col.default!r}")
            if actual_col.primary_key != expected_col.primary_key:
                parts.append(f"primary key {actual_col.primary_key} != {expected_col.primary_key}")
            incompatible.append(f"column '{name}' incompatible ({', '.join(parts)})")

        if incompatible:
            details.append(f"Table '{table}': {'; '.join(incompatible)}")

    if not details:
        return None
    return "Schema mismatch — " + " | ".join(details)


async def _repair_cache_schema(
    db: aiosqlite.Connection,
    expected: dict[str, dict[str, ColumnSpec]],
    *,
    journal_mode: str,
) -> list[str]:
    """Attempt non-destructive cache DB repair in place."""
    fixes: list[str] = []

    if journal_mode != "wal":
        cursor = await db.execute("PRAGMA journal_mode = WAL")
        row = await cursor.fetchone()
        new_journal_mode = (row[0] if row else "").lower()
        if new_journal_mode != "wal":
            raise RuntimeError("failed to enable WAL mode")
        fixes.append("enabled WAL mode")

    actual = await _load_schema(db)
    missing_tables = [table for table, cols in actual.items() if not cols]
    if missing_tables:
        cache = Cache(db)
        await cache.init_db()
        fixes.append(f"created tables: {', '.join(sorted(missing_tables))}")
        actual = await _load_schema(db)

    for table, expected_cols in expected.items():
        actual_cols = actual[table]
        missing_specs = [spec for name, spec in expected_cols.items() if name not in actual_cols]
        if not missing_specs:
            continue

        unrepairable = [spec.name for spec in missing_specs if not _can_add_column_in_place(spec)]
        if unrepairable:
            cols = ", ".join(sorted(unrepairable))
            raise RuntimeError(f"cannot safely add required columns in place for {table}: {cols}")

        for spec in missing_specs:
            definition = _column_definition_sql(spec)
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")  # noqa: S608
        await db.commit()
        fixes.append(f"added columns to {table}: {', '.join(spec.name for spec in missing_specs)}")

    return fixes


async def check_cache(settings: Settings, *, fix: bool = False) -> CheckResult:
    """Validate cache database: existence, integrity, and schema."""
    db_path = Path(settings.cache.db_path).expanduser()
    recreate_hint = f"run '{_cache_recreate_command()}' to replace the cache database"
    fix_or_recreate_hint = (
        "run 'procontext doctor --fix' to attempt in-place repair; "
        f"if that cannot fix it, {recreate_hint}"
    )

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
            fix_hint=(
                f"run 'chmod 755 {db_path.parent}'; "
                f"if the cache still cannot be opened afterward, {recreate_hint}"
            ),
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
            journal_mode = (row[0] if row else "unknown").lower()
            expected = await _expected_schema()
            actual = await _load_schema(db)

            mismatch_detail = _schema_mismatch_detail(actual, expected)
            journal_detail = None
            if journal_mode != "wal":
                journal_detail = f"Journal mode is '{journal_mode}', expected 'wal'"

            if journal_detail is None and mismatch_detail is None:
                return CheckResult("Cache", "ok", f"{db_path}, schema valid")

            if not fix:
                detail = mismatch_detail or journal_detail or f"{db_path}, schema invalid"
                return CheckResult("Cache", "fail", detail, fix_hint=fix_or_recreate_hint)

            try:
                fixes = await _repair_cache_schema(db, expected, journal_mode=journal_mode)
            except Exception as repair_exc:
                detail = mismatch_detail or journal_detail or f"{db_path}, schema invalid"
                detail = f"{detail}. In-place repair failed: {repair_exc}"
                return CheckResult("Cache", "fail", detail, fix_hint=recreate_hint)

            actual = await _load_schema(db)
            final_mismatch = _schema_mismatch_detail(actual, expected)
            cursor = await db.execute("PRAGMA journal_mode")
            row = await cursor.fetchone()
            final_journal_mode = (row[0] if row else "unknown").lower()
            if final_journal_mode != "wal" or final_mismatch is not None:
                detail = final_mismatch or (
                    f"Journal mode is '{final_journal_mode}', expected 'wal'"
                )
                return CheckResult(
                    "Cache",
                    "fail",
                    f"{detail}. In-place repair could not safely complete.",
                    fix_hint=recreate_hint,
                )

            fixes = list(dict.fromkeys(fixes))
            return CheckResult("Cache", "ok", "; ".join(fixes), fixed=True)

    except Exception as exc:
        detail = f"Database is corrupt or unreadable: {db_path} ({exc})"
        if fix:
            detail += ". In-place repair was not attempted to avoid destructive data loss."
        return CheckResult(
            "Cache",
            "fail",
            detail,
            fix_hint=recreate_hint,
        )


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
        else:
            msg += " See fix hints above for manual follow-up."
        print(msg)  # noqa: T201
        sys.exit(1)
