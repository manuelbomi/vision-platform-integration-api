"""Async dispatch queue that sits between the webhook receiver and plugins.

The receiver endpoint (``POST /webhooks/events``) must respond quickly no
matter how slow a downstream plugin is - a webhook forwarder hitting a
customer's flaky endpoint, for example, should never make the vision
platform's own webhook call time out. So the endpoint just validates the
payload and drops the resulting ``VisionEvent`` on an in-memory queue;
one or more background worker tasks pull events off that queue and run
every configured plugin against them.

Retry policy lives here, not in individual plugins:
  - A plugin with ``retryable = True`` (currently just the webhook
    forwarder) gets retried with exponential backoff, up to that plugin's
    own ``max_retries``. After that it gives up and the failure is logged.
  - A plugin with ``retryable = False`` (Slack notifier, SQL logger, ...)
    gets exactly one attempt; a failure is logged and the queue moves on to
    the next plugin/event. One plugin's bug or outage never blocks another
    plugin or backs up the whole queue.
"""

from __future__ import annotations

import asyncio
import logging

from .models import VisionEvent
from .plugins.base import BasePlugin

logger = logging.getLogger(__name__)


class DispatchQueue:
    """An asyncio-queue-backed fan-out from events to plugins."""

    def __init__(
        self,
        plugins: list[BasePlugin],
        num_workers: int = 2,
        max_queue_size: int = 1000,
    ) -> None:
        self._plugins = plugins
        self._queue: asyncio.Queue[VisionEvent] = asyncio.Queue(maxsize=max_queue_size)
        self._num_workers = num_workers
        self._workers: list[asyncio.Task] = []
        self._started = False

    @property
    def is_running(self) -> bool:
        return self._started

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._workers = [
            asyncio.create_task(self._worker_loop(i)) for i in range(self._num_workers)
        ]

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        self._started = False

    async def enqueue(self, event: VisionEvent) -> None:
        """Add an event to the queue. Returns immediately."""
        await self._queue.put(event)

    async def join(self) -> None:
        """Block until every currently-queued event has been processed.

        Mainly useful in tests, where we want a deterministic point to
        assert on plugin side effects instead of sleeping and hoping.
        """
        await self._queue.join()

    async def _worker_loop(self, worker_id: int) -> None:
        while True:
            event = await self._queue.get()
            try:
                await self._dispatch_to_plugins(event)
            except Exception:  # pragma: no cover - defensive, plugins shouldn't raise here
                logger.exception("Unexpected error dispatching event on worker %d", worker_id)
            finally:
                self._queue.task_done()

    async def _dispatch_to_plugins(self, event: VisionEvent) -> None:
        for plugin in self._plugins:
            await self._run_plugin_with_retry(plugin, event)

    async def _run_plugin_with_retry(self, plugin: BasePlugin, event: VisionEvent) -> None:
        max_retries = getattr(plugin, "max_retries", 0) if plugin.retryable else 0
        base_delay = getattr(plugin, "base_delay_seconds", 0.5)
        backoff_factor = getattr(plugin, "backoff_factor", 2.0)

        attempt = 0
        while True:
            try:
                await plugin.handle_event(event)
                return
            except Exception as exc:
                if not plugin.retryable or attempt >= max_retries:
                    logger.error(
                        "Plugin '%s' failed permanently for camera=%s event_type=%s "
                        "after %d attempt(s): %s",
                        plugin.name,
                        event.camera_id,
                        event.event_type,
                        attempt + 1,
                        exc,
                    )
                    return
                delay = base_delay * (backoff_factor**attempt)
                logger.warning(
                    "Plugin '%s' failed (attempt %d/%d), retrying in %.2fs: %s",
                    plugin.name,
                    attempt + 1,
                    max_retries,
                    delay,
                    exc,
                )
                attempt += 1
                await asyncio.sleep(delay)
