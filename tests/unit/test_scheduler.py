"""Unit tests for the registry update scheduler in schedulers.py.

Tests the scheduling loop logic by mocking check_for_registry_update and
asyncio.sleep. Each test controls a sequence of outcomes and verifies the
resulting sleep durations and loop behavior.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from procontext.config import Settings
from procontext.models.registry import RegistryIndexes
from procontext.registry import (
    REGISTRY_INITIAL_BACKOFF_SECONDS,
    REGISTRY_MAX_BACKOFF_SECONDS,
    REGISTRY_MAX_TRANSIENT_BACKOFF_ATTEMPTS,
)
from procontext.schedulers import run_registry_update_scheduler
from procontext.state import AppState


def _make_state(transport: str = "http") -> AppState:
    settings = Settings(server={"transport": transport})
    return AppState(
        settings=settings,
        indexes=RegistryIndexes(),
        registry_version="test",
    )


class TestSchedulerStdioMode:
    """stdio mode: runs once and returns, no loop."""

    async def test_stdio_runs_once_when_due(self) -> None:
        state = _make_state(transport="stdio")
        mock_check = AsyncMock(return_value="success")

        with (
            patch("procontext.schedulers.registry_check_is_due", return_value=True),
            patch("procontext.schedulers.check_for_registry_update", mock_check),
        ):
            await run_registry_update_scheduler(state)

        mock_check.assert_awaited_once_with(state)

    async def test_stdio_skips_check_when_not_due(self) -> None:
        state = _make_state(transport="stdio")
        mock_check = AsyncMock(return_value="success")

        with (
            patch("procontext.schedulers.registry_check_is_due", return_value=False),
            patch("procontext.schedulers.check_for_registry_update", mock_check),
        ):
            await run_registry_update_scheduler(state)

        mock_check.assert_not_awaited()

    async def test_stdio_skip_initial_check(self) -> None:
        state = _make_state(transport="stdio")
        mock_check = AsyncMock(return_value="success")

        with patch("procontext.schedulers.check_for_registry_update", mock_check):
            await run_registry_update_scheduler(state, skip_initial_check=True)

        mock_check.assert_not_awaited()

    async def test_stdio_swallows_exception(self) -> None:
        state = _make_state(transport="stdio")
        mock_check = AsyncMock(side_effect=RuntimeError("network down"))

        with (
            patch("procontext.schedulers.registry_check_is_due", return_value=True),
            patch("procontext.schedulers.check_for_registry_update", mock_check),
        ):
            await run_registry_update_scheduler(state)

        mock_check.assert_awaited_once()


class TestSchedulerHttpMode:
    """HTTP mode: loops with outcome-dependent sleep durations."""

    async def test_success_sleeps_24h(self) -> None:
        state = _make_state(transport="http")
        sleep_durations: list[float] = []

        async def fake_sleep(duration: float) -> None:
            sleep_durations.append(duration)
            raise asyncio.CancelledError

        mock_check = AsyncMock(return_value="success")

        with (
            patch("procontext.schedulers.check_for_registry_update", mock_check),
            patch("asyncio.sleep", side_effect=fake_sleep),
            pytest.raises(asyncio.CancelledError),
        ):
            await run_registry_update_scheduler(state)

        assert sleep_durations[0] == state.settings.registry.poll_interval_hours * 3600

    async def test_semantic_failure_sleeps_24h(self) -> None:
        state = _make_state(transport="http")
        sleep_durations: list[float] = []

        async def fake_sleep(duration: float) -> None:
            sleep_durations.append(duration)
            raise asyncio.CancelledError

        mock_check = AsyncMock(return_value="semantic_failure")

        with (
            patch("procontext.schedulers.check_for_registry_update", mock_check),
            patch("asyncio.sleep", side_effect=fake_sleep),
            pytest.raises(asyncio.CancelledError),
        ):
            await run_registry_update_scheduler(state)

        assert sleep_durations[0] == state.settings.registry.poll_interval_hours * 3600

    async def test_transient_failure_uses_backoff(self) -> None:
        state = _make_state(transport="http")
        sleep_durations: list[float] = []

        async def fake_sleep(duration: float) -> None:
            sleep_durations.append(duration)
            if len(sleep_durations) >= 3:
                raise asyncio.CancelledError

        mock_check = AsyncMock(return_value="transient_failure")

        with (
            patch("procontext.schedulers.check_for_registry_update", mock_check),
            patch("asyncio.sleep", side_effect=fake_sleep),
            patch(
                "procontext.schedulers._jittered_delay",
                side_effect=lambda seconds: float(seconds),
            ),
            pytest.raises(asyncio.CancelledError),
        ):
            await run_registry_update_scheduler(state)

        assert sleep_durations[0] == REGISTRY_INITIAL_BACKOFF_SECONDS
        assert sleep_durations[1] == REGISTRY_INITIAL_BACKOFF_SECONDS * 2
        assert sleep_durations[2] == REGISTRY_INITIAL_BACKOFF_SECONDS * 4

    async def test_backoff_capped_at_max(self) -> None:
        state = _make_state(transport="http")
        sleep_durations: list[float] = []

        async def fake_sleep(duration: float) -> None:
            sleep_durations.append(duration)
            if len(sleep_durations) >= 7:
                raise asyncio.CancelledError

        mock_check = AsyncMock(return_value="transient_failure")

        with (
            patch("procontext.schedulers.check_for_registry_update", mock_check),
            patch("asyncio.sleep", side_effect=fake_sleep),
            patch(
                "procontext.schedulers._jittered_delay",
                side_effect=lambda seconds: float(seconds),
            ),
            pytest.raises(asyncio.CancelledError),
        ):
            await run_registry_update_scheduler(state)

        assert sleep_durations == [60, 120, 240, 480, 960, 1920, REGISTRY_MAX_BACKOFF_SECONDS]

    async def test_circuit_breaker_fires_at_threshold(self) -> None:
        state = _make_state(transport="http")
        sleep_durations: list[float] = []
        call_count = 0

        async def fake_sleep(duration: float) -> None:
            nonlocal call_count
            sleep_durations.append(duration)
            call_count += 1
            if call_count >= REGISTRY_MAX_TRANSIENT_BACKOFF_ATTEMPTS:
                raise asyncio.CancelledError

        mock_check = AsyncMock(return_value="transient_failure")

        with (
            patch("procontext.schedulers.check_for_registry_update", mock_check),
            patch("asyncio.sleep", side_effect=fake_sleep),
            patch(
                "procontext.schedulers._jittered_delay",
                side_effect=lambda seconds: float(seconds),
            ),
            pytest.raises(asyncio.CancelledError),
        ):
            await run_registry_update_scheduler(state)

        assert sleep_durations[-1] == state.settings.registry.poll_interval_hours * 3600

    async def test_circuit_breaker_resets_counter(self) -> None:
        state = _make_state(transport="http")
        sleep_durations: list[float] = []
        call_count = 0

        async def fake_sleep(duration: float) -> None:
            nonlocal call_count
            sleep_durations.append(duration)
            call_count += 1
            if call_count >= REGISTRY_MAX_TRANSIENT_BACKOFF_ATTEMPTS + 1:
                raise asyncio.CancelledError

        mock_check = AsyncMock(return_value="transient_failure")

        with (
            patch("procontext.schedulers.check_for_registry_update", mock_check),
            patch("asyncio.sleep", side_effect=fake_sleep),
            patch(
                "procontext.schedulers._jittered_delay",
                side_effect=lambda seconds: float(seconds),
            ),
            pytest.raises(asyncio.CancelledError),
        ):
            await run_registry_update_scheduler(state)

        assert sleep_durations[-2] == state.settings.registry.poll_interval_hours * 3600
        assert sleep_durations[-1] == REGISTRY_INITIAL_BACKOFF_SECONDS

    async def test_success_resets_backoff(self) -> None:
        state = _make_state(transport="http")
        sleep_durations: list[float] = []

        outcomes = ["transient_failure", "transient_failure", "success", "transient_failure"]
        mock_check = AsyncMock(side_effect=outcomes)

        async def fake_sleep(duration: float) -> None:
            sleep_durations.append(duration)
            if len(sleep_durations) >= 4:
                raise asyncio.CancelledError

        with (
            patch("procontext.schedulers.check_for_registry_update", mock_check),
            patch("asyncio.sleep", side_effect=fake_sleep),
            patch(
                "procontext.schedulers._jittered_delay",
                side_effect=lambda seconds: float(seconds),
            ),
            pytest.raises(asyncio.CancelledError),
        ):
            await run_registry_update_scheduler(state)

        assert sleep_durations[0] == REGISTRY_INITIAL_BACKOFF_SECONDS
        assert sleep_durations[1] == REGISTRY_INITIAL_BACKOFF_SECONDS * 2
        assert sleep_durations[2] == state.settings.registry.poll_interval_hours * 3600
        assert sleep_durations[3] == REGISTRY_INITIAL_BACKOFF_SECONDS

    async def test_http_skip_initial_check_sleeps_before_first_poll(self) -> None:
        """With skip_initial_check=True in HTTP mode the scheduler sleeps for the
        full poll interval BEFORE the first check, then resumes normal cadence.

        Sequence: sleep(24h) → check → sleep(24h) → cancel
        """
        state = _make_state(transport="http")
        sleep_durations: list[float] = []

        async def fake_sleep(duration: float) -> None:
            sleep_durations.append(duration)
            if len(sleep_durations) >= 2:
                raise asyncio.CancelledError

        mock_check = AsyncMock(return_value="success")

        with (
            patch("procontext.schedulers.check_for_registry_update", mock_check),
            patch("asyncio.sleep", side_effect=fake_sleep),
            pytest.raises(asyncio.CancelledError),
        ):
            await run_registry_update_scheduler(state, skip_initial_check=True)

        # First sleep happens before any check — the deferred initial poll.
        assert sleep_durations[0] == state.settings.registry.poll_interval_hours * 3600
        # Check fires exactly once, after the initial sleep.
        mock_check.assert_awaited_once()
        # Normal post-success sleep follows the check.
        assert sleep_durations[1] == state.settings.registry.poll_interval_hours * 3600

    async def test_unexpected_exception_treated_as_semantic(self) -> None:
        state = _make_state(transport="http")
        sleep_durations: list[float] = []

        mock_check = AsyncMock(side_effect=RuntimeError("unexpected"))

        async def fake_sleep(duration: float) -> None:
            sleep_durations.append(duration)
            raise asyncio.CancelledError

        with (
            patch("procontext.schedulers.check_for_registry_update", mock_check),
            patch("asyncio.sleep", side_effect=fake_sleep),
            pytest.raises(asyncio.CancelledError),
        ):
            await run_registry_update_scheduler(state)

        assert sleep_durations[0] == state.settings.registry.poll_interval_hours * 3600
