"""CLI entrypoint and registry bootstrap logic for ProContext."""

from __future__ import annotations

import asyncio
import sys

import structlog
from pydantic import ValidationError

from procontext.config import Settings
from procontext.fetcher import build_http_client
from procontext.logging_config import setup_logging
from procontext.mcp.lifespan import registry_paths
from procontext.registry import fetch_registry_for_setup, load_registry
from procontext.transport import run_http_server

log = structlog.get_logger()


async def _attempt_registry_setup(settings: Settings) -> bool:
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


async def _ensure_registry(settings: Settings) -> bool:
    """Check registry availability, attempt auto-setup if needed. Returns True if ready."""
    registry_path, registry_state_path = registry_paths(settings)
    if load_registry(local_registry_path=registry_path, local_state_path=registry_state_path):
        return True
    log.info("registry_not_found_attempting_auto_setup")
    await _attempt_registry_setup(settings)
    return (
        load_registry(local_registry_path=registry_path, local_state_path=registry_state_path)
        is not None
    )


async def _run_setup(settings: Settings) -> None:
    """Fetch the registry from the configured URL and save it to the data directory."""
    registry_path, _ = registry_paths(settings)
    print(  # noqa: T201 — CLI command, not MCP server
        f"Downloading registry from {settings.registry.metadata_url} ...",
        flush=True,
    )

    if await _attempt_registry_setup(settings):
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


def main() -> None:
    try:
        settings = Settings()
    except ValidationError as exc:
        print(f"Configuration error:\n{exc}", file=sys.stderr)  # noqa: T201
        sys.exit(1)

    setup_logging(settings)

    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        asyncio.run(_run_setup(settings))
        return

    if not asyncio.run(_ensure_registry(settings)):
        log.critical(
            "registry_not_initialised",
            hint="Run 'procontext setup' to download the registry.",
        )
        sys.exit(1)

    from procontext.mcp.server import mcp  # imported here to avoid circular import at module level

    if settings.server.transport == "http":
        run_http_server(mcp, settings)
        return

    mcp.run()


if __name__ == "__main__":
    main()
