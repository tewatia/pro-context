"""Tests for MCPSecurityMiddleware (Phase 4 — HTTP transport).

Each test exercises the middleware directly via httpx's ASGI transport so no
real server is started.  The inner app is a trivial 200-OK echo that never
runs if the middleware short-circuits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest

from procontext.transport import SUPPORTED_PROTOCOL_VERSIONS, MCPSecurityMiddleware

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _ok_app(scope: Scope, receive: Receive, send: Send) -> None:
    """Minimal ASGI app that always returns 200 OK."""
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _client(app: ASGIApp) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost",
    )


# ---------------------------------------------------------------------------
# Auth disabled (default)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_disabled_allows_any_request() -> None:
    app = MCPSecurityMiddleware(_ok_app, auth_enabled=False)
    async with _client(app) as client:
        response = await client.get("/mcp")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_auth_disabled_allows_request_with_auth_header() -> None:
    """Even if a client sends a bearer token, it is ignored when auth is off."""
    app = MCPSecurityMiddleware(_ok_app, auth_enabled=False)
    async with _client(app) as client:
        response = await client.get("/mcp", headers={"Authorization": "Bearer whatever"})
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Auth enabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_enabled_correct_key_passes() -> None:
    app = MCPSecurityMiddleware(_ok_app, auth_enabled=True, auth_key="secret-key")
    async with _client(app) as client:
        response = await client.get("/mcp", headers={"Authorization": "Bearer secret-key"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_auth_enabled_wrong_key_returns_401() -> None:
    app = MCPSecurityMiddleware(_ok_app, auth_enabled=True, auth_key="secret-key")
    async with _client(app) as client:
        response = await client.get("/mcp", headers={"Authorization": "Bearer wrong-key"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_enabled_missing_header_returns_401() -> None:
    app = MCPSecurityMiddleware(_ok_app, auth_enabled=True, auth_key="secret-key")
    async with _client(app) as client:
        response = await client.get("/mcp")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_enabled_malformed_header_returns_401() -> None:
    """Header present but not in 'Bearer <key>' format."""
    app = MCPSecurityMiddleware(_ok_app, auth_enabled=True, auth_key="secret-key")
    async with _client(app) as client:
        response = await client.get("/mcp", headers={"Authorization": "secret-key"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Origin validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost",
        "http://localhost:8080",
        "https://localhost",
        "https://localhost:9000",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
    ],
)
@pytest.mark.asyncio
async def test_origin_localhost_allowed(origin: str) -> None:
    app = MCPSecurityMiddleware(_ok_app, auth_enabled=False)
    async with _client(app) as client:
        response = await client.get("/mcp", headers={"Origin": origin})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.com",
        "http://attacker.localhost.evil.com",
        "http://192.168.1.1",
        "http://0.0.0.0",
    ],
)
@pytest.mark.asyncio
async def test_origin_external_blocked(origin: str) -> None:
    app = MCPSecurityMiddleware(_ok_app, auth_enabled=False)
    async with _client(app) as client:
        response = await client.get("/mcp", headers={"Origin": origin})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_no_origin_header_allowed() -> None:
    """CLI tools and non-browser clients don't send Origin — must be allowed."""
    app = MCPSecurityMiddleware(_ok_app, auth_enabled=False)
    async with _client(app) as client:
        response = await client.get("/mcp")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Protocol version validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("version", sorted(SUPPORTED_PROTOCOL_VERSIONS))
@pytest.mark.asyncio
async def test_known_protocol_version_allowed(version: str) -> None:
    app = MCPSecurityMiddleware(_ok_app, auth_enabled=False)
    async with _client(app) as client:
        response = await client.get("/mcp", headers={"MCP-Protocol-Version": version})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_unknown_protocol_version_blocked() -> None:
    app = MCPSecurityMiddleware(_ok_app, auth_enabled=False)
    async with _client(app) as client:
        response = await client.get("/mcp", headers={"MCP-Protocol-Version": "1999-01-01"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_absent_protocol_version_allowed() -> None:
    """Clients that omit the header are not rejected."""
    app = MCPSecurityMiddleware(_ok_app, auth_enabled=False)
    async with _client(app) as client:
        response = await client.get("/mcp")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Check ordering: auth is evaluated before origin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_checked_before_origin() -> None:
    """With auth enabled, a bad key returns 401 even if origin would be forbidden."""
    app = MCPSecurityMiddleware(_ok_app, auth_enabled=True, auth_key="key")
    async with _client(app) as client:
        response = await client.get(
            "/mcp",
            headers={"Authorization": "Bearer wrong", "Origin": "https://evil.com"},
        )
    assert response.status_code == 401
