"""Background scheduler coroutines for registry updates and cache cleanup."""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

import structlog

from procontext.registry import (
    REGISTRY_INITIAL_BACKOFF_SECONDS,
    REGISTRY_MAX_BACKOFF_SECONDS,
    REGISTRY_MAX_TRANSIENT_BACKOFF_ATTEMPTS,
    check_for_registry_update,
    registry_check_is_due,
)

if TYPE_CHECKING:
    from procontext.state import AppState

log = structlog.get_logger()


def _jittered_delay(base_seconds: int) -> float:
    return base_seconds * random.uniform(0.8, 1.2)


async def run_cache_cleanup_scheduler(state: AppState) -> None:
    """Run cache cleanup at startup and (HTTP mode) on the configured interval."""
    interval_hours = state.settings.cache.cleanup_interval_hours

    # Both transports: run at startup, skipping if it ran recently.
    if state.cache is not None:
        await state.cache.cleanup_if_due(interval_hours)

    if state.settings.server.transport != "http":
        return

    # HTTP long-running mode: repeat on the configured interval.
    while True:
        await asyncio.sleep(interval_hours * 3600)
        if state.cache is not None:
            await state.cache.cleanup_if_due(interval_hours)


async def run_registry_update_scheduler(
    state: AppState,
    *,
    skip_initial_check: bool = False,
) -> None:
    """Run startup update check and (HTTP mode) periodic registry update checks."""
    if state.settings.server.transport != "http":
        if not skip_initial_check:
            poll_interval = state.settings.registry.poll_interval_hours
            if registry_check_is_due(state.registry_state_path, poll_interval):
                try:
                    await check_for_registry_update(state)
                except Exception:
                    log.warning(
                        "registry_update_scheduler_error", mode="startup_once", exc_info=True
                    )
        return

    backoff_seconds = REGISTRY_INITIAL_BACKOFF_SECONDS
    consecutive_transient_failures = 0

    if skip_initial_check:
        await asyncio.sleep(state.settings.registry.poll_interval_hours * 3600)

    while True:
        try:
            outcome = await check_for_registry_update(state)
        except Exception:
            log.warning("registry_update_scheduler_error", mode="http_loop", exc_info=True)
            outcome = "semantic_failure"

        poll_interval_seconds = state.settings.registry.poll_interval_hours * 3600

        if outcome == "success":
            consecutive_transient_failures = 0
            backoff_seconds = REGISTRY_INITIAL_BACKOFF_SECONDS
            await asyncio.sleep(poll_interval_seconds)
            continue

        if outcome == "transient_failure":
            consecutive_transient_failures += 1
            if consecutive_transient_failures >= REGISTRY_MAX_TRANSIENT_BACKOFF_ATTEMPTS:
                log.warning(
                    "registry_update_transient_retry_suspended",
                    consecutive_failures=consecutive_transient_failures,
                    cooldown_seconds=poll_interval_seconds,
                )
                consecutive_transient_failures = 0
                backoff_seconds = REGISTRY_INITIAL_BACKOFF_SECONDS
                await asyncio.sleep(poll_interval_seconds)
                continue

            await asyncio.sleep(_jittered_delay(backoff_seconds))
            backoff_seconds = min(backoff_seconds * 2, REGISTRY_MAX_BACKOFF_SECONDS)
            continue

        # semantic failure
        consecutive_transient_failures = 0
        backoff_seconds = REGISTRY_INITIAL_BACKOFF_SECONDS
        await asyncio.sleep(poll_interval_seconds)
