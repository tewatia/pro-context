"""Non-cache system checks used by the doctor command."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from procontext.cli import cmd_setup
from procontext.cli.doctor.models import CheckResult
from procontext.config import registry_paths

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from procontext.config import FetcherSettings, Settings
    from procontext.models.registry import RegistryEntry


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

    if not os.access(data_dir, os.R_OK | os.W_OK | os.X_OK):
        return CheckResult(
            "Data directory",
            "fail",
            f"Insufficient permissions on {data_dir}",
            fix_hint=f"run 'chmod 755 {data_dir}'",
        )

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


async def check_registry(
    settings: Settings,
    *,
    fix: bool = False,
    load_registry_fn: Callable[..., tuple[Sequence[RegistryEntry], str] | None],
) -> CheckResult:
    """Validate registry files are present, parseable, and checksum-valid."""
    registry_path, registry_state_path = registry_paths(settings)

    result = load_registry_fn(
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

    if fix:
        try:
            success = await cmd_setup.attempt_registry_setup(settings)
        except (OSError, httpx.HTTPError) as exc:
            return CheckResult(
                "Registry",
                "fail",
                f"Download failed: {exc}",
            )
        if success:
            reloaded = load_registry_fn(
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


async def check_network(
    settings: Settings,
    *,
    fix: bool = False,
    client_builder: Callable[[FetcherSettings | None], httpx.AsyncClient],
) -> CheckResult:
    """Check network connectivity to the registry metadata URL."""
    del fix
    http_client = client_builder(settings.fetcher)
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
