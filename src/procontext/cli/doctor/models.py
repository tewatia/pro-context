"""Shared result and schema models for doctor checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


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
