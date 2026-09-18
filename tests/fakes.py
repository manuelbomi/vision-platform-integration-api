"""Fake plugins used across the test suite.

These live outside any single test module so they can be reused between the
HTTP-level endpoint tests and the lower-level dispatch retry tests.
"""

from __future__ import annotations

from typing import Any

from api.models import VisionEvent
from api.plugins.base import BasePlugin


class RecordingPlugin(BasePlugin):
    """Records every event it receives; never fails."""

    name = "recording"
    retryable = False

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.calls: list[VisionEvent] = []

    async def handle_event(self, event: VisionEvent) -> None:
        self.calls.append(event)


class FlakyPlugin(BasePlugin):
    """Fails `fail_times` times, then succeeds. Retryable by DispatchQueue.

    Config:
        fail_times: number of calls that should raise before succeeding
        max_retries, base_delay_seconds, backoff_factor: read by
            DispatchQueue to control the retry loop.
    """

    name = "flaky"
    retryable = True

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.fail_times: int = self.config.get("fail_times", 0)
        self.max_retries: int = self.config.get("max_retries", 3)
        self.base_delay_seconds: float = self.config.get("base_delay_seconds", 0.01)
        self.backoff_factor: float = self.config.get("backoff_factor", 1.0)
        self.attempts = 0

    async def handle_event(self, event: VisionEvent) -> None:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise RuntimeError(f"simulated failure #{self.attempts}")
