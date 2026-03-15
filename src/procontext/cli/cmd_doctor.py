"""CLI command: procontext doctor — validate system health and optionally repair."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from procontext.cli.doctor.cache_check import check_cache as _check_cache
from procontext.cli.doctor.cache_check import expected_schema as _expected_schema
from procontext.cli.doctor.checks import (
    check_data_dir as _check_data_dir,
    check_network as _check_network,
    check_registry as _check_registry,
)
from procontext.cli.doctor.models import CheckResult
from procontext.cli.doctor.output import format_result as _format_result
from procontext.fetcher import build_http_client
from procontext.registry import load_registry

if TYPE_CHECKING:
    from procontext.config import Settings

async def check_data_dir(settings: Settings, *, fix: bool = False) -> CheckResult:
    """Validate data directory exists with proper permissions."""
    return await _check_data_dir(settings, fix=fix)

async def check_registry(settings: Settings, *, fix: bool = False) -> CheckResult:
    """Validate registry files are present, parseable, and checksum-valid."""
    return await _check_registry(
        settings,
        fix=fix,
        load_registry_fn=load_registry,
    )


async def check_cache(settings: Settings, *, fix: bool = False) -> CheckResult:
    """Validate cache database: existence, integrity, and schema."""
    return await _check_cache(settings, fix=fix)


async def check_network(settings: Settings, *, fix: bool = False) -> CheckResult:
    """Check network connectivity to the registry metadata URL."""
    return await _check_network(
        settings,
        fix=fix,
        client_builder=build_http_client,
    )


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
