"""Unit tests for the default CLI server command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from procontext.cli import cmd_serve
from procontext.config import Settings


def _return_from_asyncio_run(result: bool):
    """Return a fake asyncio.run that closes the coroutine and returns *result*."""

    def _fake_run(coro):  # type: ignore[no-untyped-def]
        coro.close()
        return result

    return _fake_run


def test_run_server_dispatches_http_transport() -> None:
    settings = Settings(server={"transport": "http"})
    fake_mcp = MagicMock()

    with (
        patch("procontext.cli.cmd_serve.asyncio.run", side_effect=_return_from_asyncio_run(True)),
        patch("procontext.cli.cmd_serve.mcp", fake_mcp),
        patch("procontext.cli.cmd_serve.run_http_server") as mock_run_http_server,
    ):
        cmd_serve.run_server(settings)

    mock_run_http_server.assert_called_once_with(fake_mcp, settings)
    fake_mcp.run.assert_not_called()


def test_run_server_dispatches_stdio_transport() -> None:
    settings = Settings(server={"transport": "stdio"})
    fake_mcp = MagicMock()

    with (
        patch("procontext.cli.cmd_serve.asyncio.run", side_effect=_return_from_asyncio_run(True)),
        patch("procontext.cli.cmd_serve.mcp", fake_mcp),
        patch("procontext.cli.cmd_serve.run_http_server") as mock_run_http_server,
    ):
        cmd_serve.run_server(settings)

    mock_run_http_server.assert_not_called()
    fake_mcp.run.assert_called_once_with()
