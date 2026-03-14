"""CLI command: procontext (no subcommand) — start the MCP server."""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

import structlog

from procontext.config import registry_paths
from procontext.mcp.server import mcp
from procontext.registry import load_registry
from procontext.transport import run_http_server

if TYPE_CHECKING:
    from procontext.config import Settings

log = structlog.get_logger()


async def _ensure_registry(settings: Settings) -> bool:
    """Check registry availability, attempt auto-setup if needed. Returns True if ready."""
    registry_path, registry_state_path = registry_paths(settings)
    if load_registry(local_registry_path=registry_path, local_state_path=registry_state_path):
        return True

    log.info("registry_not_found_attempting_auto_setup")

    # Deferred: avoid loading setup/download machinery when the registry
    # already exists (the common path returns early above).
    from procontext.cli.cmd_setup import attempt_registry_setup

    await attempt_registry_setup(settings)
    return (
        load_registry(local_registry_path=registry_path, local_state_path=registry_state_path)
        is not None
    )


def run_server(settings: Settings) -> None:
    """Ensure the registry is present and launch the MCP server."""
    if not asyncio.run(_ensure_registry(settings)):
        log.critical(
            "registry_not_initialised",
            hint="Run 'procontext setup' to download the registry.",
        )
        sys.exit(1)

    if settings.server.transport == "http":
        run_http_server(mcp, settings)
        return

    mcp.run()
