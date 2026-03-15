"""Cache database validation and in-place repair logic for doctor."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite

from procontext.cache import Cache
from procontext.cli.doctor.models import CheckResult, ColumnSpec

if TYPE_CHECKING:
    from procontext.config import Settings


def cache_recreate_command() -> str:
    """Return the CLI command that force-recreates the cache DB."""
    return "procontext db recreate"


async def expected_schema() -> dict[str, dict[str, ColumnSpec]]:
    """Build the expected cache schema using an in-memory database."""
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
    return not (spec.not_null and spec.default is None)


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
    recreate_hint = f"run '{cache_recreate_command()}' to replace the cache database"
    fix_or_recreate_hint = (
        "run 'procontext doctor --fix' to attempt in-place repair; "
        f"if that cannot fix it, {recreate_hint}"
    )

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

    if not db_path.exists():
        return CheckResult(
            "Cache",
            "warn",
            f"Database will be created on first run: {db_path}",
        )

    try:
        async with aiosqlite.connect(str(db_path)) as db:
            cursor = await db.execute("PRAGMA journal_mode")
            row = await cursor.fetchone()
            journal_mode = (row[0] if row else "unknown").lower()
            expected = await expected_schema()
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
            except (aiosqlite.Error, RuntimeError) as repair_exc:
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

    except (aiosqlite.Error, OSError) as exc:
        detail = f"Database is corrupt or unreadable: {db_path} ({exc})"
        if fix:
            detail += ". In-place repair was not attempted to avoid destructive data loss."
        return CheckResult(
            "Cache",
            "fail",
            detail,
            fix_hint=recreate_hint,
        )
