"""CLI command: procontext setup — download and persist the library registry."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from procontext.config import registry_paths
from procontext.fetcher import build_http_client
from procontext.registry import fetch_registry_for_setup

if TYPE_CHECKING:
    from procontext.config import Settings


async def attempt_registry_setup(settings: Settings) -> bool:
    """Try to fetch and persist the registry once. Returns True on success."""
    registry_path, registry_state_path = registry_paths(settings)
    http_client = build_http_client(settings.fetcher)
    try:
        return await fetch_registry_for_setup(
            http_client=http_client,
            metadata_url=settings.registry.metadata_url,
            registry_path=registry_path,
            registry_state_path=registry_state_path,
        )
    finally:
        await http_client.aclose()


async def run_setup(settings: Settings) -> None:
    """Fetch the registry from the configured URL and save it to the data directory."""
    registry_path, _ = registry_paths(settings)
    print(  # noqa: T201 — CLI command, not MCP server
        f"Downloading registry from {settings.registry.metadata_url} ...",
        flush=True,
    )

    if await attempt_registry_setup(settings):
        print(  # noqa: T201 — CLI command, not MCP server
            f"Registry initialised (saved to: {registry_path})",
            flush=True,
        )
    else:
        print(  # noqa: T201 — CLI command, not MCP server
            "Setup failed. Check your network and try again.\n"
            "If the error persists, you can manually download the registry\n"
            "and configure its path in procontext.yaml",
            file=sys.stderr,
        )
        sys.exit(1)
