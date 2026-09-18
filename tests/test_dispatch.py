"""Dispatch queue retry logic, exercised directly (no HTTP layer needed).

Uses plain `asyncio.run` rather than pytest-asyncio, so the test suite
doesn't need an extra dependency just for these two tests. Backoff delays
are configured very short so the suite still runs fast.
"""

from __future__ import annotations

import asyncio

from api.dispatch import DispatchQueue
from api.models import VisionEvent

from .fakes import FlakyPlugin, RecordingPlugin


def _make_event() -> VisionEvent:
    return VisionEvent(
        camera_id="cam-1",
        event_type="test_event",
        confidence=0.5,
        timestamp="2026-01-01T00:00:00Z",
        metadata={},
    )


def test_dispatch_retries_until_plugin_succeeds() -> None:
    async def run() -> None:
        plugin = FlakyPlugin(
            {"fail_times": 2, "max_retries": 5, "base_delay_seconds": 0.01, "backoff_factor": 1.0}
        )
        queue = DispatchQueue([plugin], num_workers=1)
        await queue.start()
        try:
            await queue.enqueue(_make_event())
            await queue.join()
        finally:
            await queue.stop()

        # Failed on attempts 1 and 2, succeeded on attempt 3.
        assert plugin.attempts == 3

    asyncio.run(run())


def test_dispatch_gives_up_after_max_retries() -> None:
    async def run() -> None:
        plugin = FlakyPlugin(
            {
                "fail_times": 999,
                "max_retries": 2,
                "base_delay_seconds": 0.01,
                "backoff_factor": 1.0,
            }
        )
        queue = DispatchQueue([plugin], num_workers=1)
        await queue.start()
        try:
            await queue.enqueue(_make_event())
            await queue.join()
        finally:
            await queue.stop()

        # Initial attempt + 2 retries = 3 total attempts, then it gives up.
        assert plugin.attempts == 3

    asyncio.run(run())


def test_non_retryable_plugin_failure_does_not_block_other_plugins() -> None:
    async def run() -> None:
        class AlwaysFails(FlakyPlugin):
            retryable = False

        failing = AlwaysFails({"fail_times": 999})
        recorder = RecordingPlugin()
        queue = DispatchQueue([failing, recorder], num_workers=1)
        await queue.start()
        try:
            await queue.enqueue(_make_event())
            await queue.join()
        finally:
            await queue.stop()

        # The failing plugin only gets one attempt (not retryable)...
        assert failing.attempts == 1
        # ...and its failure does not stop the recorder plugin from running.
        assert len(recorder.calls) == 1

    asyncio.run(run())
