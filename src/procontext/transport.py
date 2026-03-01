"""Streamable HTTP transport and security middleware for the MCP server."""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING

import structlog
import uvicorn
from starlette.datastructures import Headers
from starlette.responses import Response

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from starlette.types import ASGIApp, Receive, Scope, Send

    from procontext.config import Settings

log = structlog.get_logger()

SUPPORTED_PROTOCOL_VERSIONS: frozenset[str] = frozenset({"2025-11-25", "2025-03-26"})
_LOCALHOST_ORIGIN = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")


class MCPSecurityMiddleware:
    """Pure ASGI middleware for HTTP transport security.

    Enforces three checks on every HTTP request:
    1. Optional bearer key authentication.
    2. Origin validation (localhost only) to prevent DNS rebinding.
    3. Protocol version validation via MCP-Protocol-Version header.

    Implemented as pure ASGI (not BaseHTTPMiddleware) so that SSE streaming
    responses are never buffered by the middleware layer.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        auth_enabled: bool,
        auth_key: str | None = None,
    ) -> None:
        self.app = app
        self.auth_enabled = auth_enabled
        self.auth_key = auth_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = Headers(scope=scope)

            # 1. Optional bearer key authentication
            if self.auth_enabled:
                auth_header = headers.get("authorization", "")
                if not auth_header.startswith("Bearer ") or auth_header[7:] != self.auth_key:
                    await Response("Unauthorized", status_code=401)(scope, receive, send)
                    return

            # 2. Origin validation — prevents DNS rebinding attacks
            origin = headers.get("origin", "")
            if origin and not _LOCALHOST_ORIGIN.match(origin):
                await Response("Forbidden", status_code=403)(scope, receive, send)
                return

            # 3. Protocol version — reject unknown versions early
            proto_version = headers.get("mcp-protocol-version", "")
            if proto_version and proto_version not in SUPPORTED_PROTOCOL_VERSIONS:
                await Response(
                    f"Unsupported protocol version: {proto_version}",
                    status_code=400,
                )(scope, receive, send)
                return

        await self.app(scope, receive, send)


def run_http_server(mcp: FastMCP, settings: Settings) -> None:
    """Start the MCP server with Streamable HTTP transport."""
    http_log = log.bind(transport="http")

    auth_key: str | None = settings.server.auth_key or None

    if settings.server.auth_enabled and not auth_key:
        auth_key = secrets.token_urlsafe(32)
        http_log.warning("http_auth_key_auto_generated", auth_key=auth_key)

    if not settings.server.auth_enabled:
        http_log.warning("http_auth_disabled")

    http_app = mcp.streamable_http_app()
    secured_app = MCPSecurityMiddleware(
        http_app,
        auth_enabled=settings.server.auth_enabled,
        auth_key=auth_key,
    )

    uvicorn.run(
        secured_app,
        host=settings.server.host,
        port=settings.server.port,
        log_config=None,  # Disable uvicorn's default logging; structlog handles it
    )
