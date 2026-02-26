"""Unit tests for the first-run blocking registry fetch in server.py."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from procontext.config import Settings
from procontext.registry import RegistryIndexes
from procontext.server import _maybe_blocking_first_run_fetch
from procontext.state import AppState


def _make_state() -> AppState:
    settings = Settings()
    return AppState(
        settings=settings,
        indexes=RegistryIndexes(),
        registry_version="unknown",
    )


class TestMaybeBlockingFirstRunFetch:
    """Tests for _maybe_blocking_first_run_fetch."""

    async def test_success_updates_state(self) -> None:
        state = _make_state()

        async def fake_check(s: AppState) -> str:
            s.registry_version = "v1.0.0"
            return "success"

        mock_check = AsyncMock(side_effect=fake_check)

        with patch("procontext.server.check_for_registry_update", mock_check):
            result = await _maybe_blocking_first_run_fetch(state)

        assert result is True
        mock_check.assert_awaited_once_with(state)

    async def test_timeout_falls_back(self) -> None:
        state = _make_state()

        async def slow_check(_: AppState) -> str:
            await asyncio.sleep(60)
            return "success"

        mock_check = AsyncMock(side_effect=slow_check)
        mock_warning = MagicMock()

        with (
            patch("procontext.server.check_for_registry_update", mock_check),
            patch("procontext.server.FIRST_RUN_FETCH_TIMEOUT_SECONDS", 0.01),
            patch("procontext.server._log_bundled_registry_warning", mock_warning),
        ):
            result = await _maybe_blocking_first_run_fetch(state)

        assert result is False
        mock_warning.assert_called_once()

    async def test_transient_failure_falls_back(self) -> None:
        state = _make_state()
        mock_check = AsyncMock(return_value="transient_failure")
        mock_warning = MagicMock()

        with (
            patch("procontext.server.check_for_registry_update", mock_check),
            patch("procontext.server._log_bundled_registry_warning", mock_warning),
        ):
            result = await _maybe_blocking_first_run_fetch(state)

        assert result is False
        mock_warning.assert_called_once()

    async def test_semantic_failure_falls_back(self) -> None:
        state = _make_state()
        mock_check = AsyncMock(return_value="semantic_failure")
        mock_warning = MagicMock()

        with (
            patch("procontext.server.check_for_registry_update", mock_check),
            patch("procontext.server._log_bundled_registry_warning", mock_warning),
        ):
            result = await _maybe_blocking_first_run_fetch(state)

        assert result is False
        mock_warning.assert_called_once()

    async def test_exception_falls_back(self) -> None:
        state = _make_state()
        mock_check = AsyncMock(side_effect=RuntimeError("network down"))
        mock_warning = MagicMock()

        with (
            patch("procontext.server.check_for_registry_update", mock_check),
            patch("procontext.server._log_bundled_registry_warning", mock_warning),
        ):
            result = await _maybe_blocking_first_run_fetch(state)

        assert result is False
        mock_warning.assert_called_once()

    async def test_bundled_warning_message_content(self) -> None:
        """Verify the warning contains all three actionable next steps."""
        state = _make_state()
        mock_check = AsyncMock(return_value="transient_failure")
        captured_calls: list[dict] = []

        def capture_warning(event: str, **kwargs: object) -> None:
            captured_calls.append({"event": event, **kwargs})

        with (
            patch("procontext.server.check_for_registry_update", mock_check),
            patch("procontext.server.log") as mock_log,
        ):
            mock_log.warning = capture_warning
            mock_log.info = lambda *a, **kw: None
            await _maybe_blocking_first_run_fetch(state)

        warning_calls = [
            c for c in captured_calls if c["event"] == "registry_using_bundled_snapshot"
        ]
        assert len(warning_calls) == 1

        message = warning_calls[0]["message"]
        assert "Check your internet connection" in message
        assert "Try restarting the server later" in message
        assert "download the registry manually" in message
