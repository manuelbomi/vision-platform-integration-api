"""Plugin interface.

Plugins are intentionally dumb: given an event, do one thing with it. All
cross-cutting concerns (queueing, concurrency, retries, isolating one
plugin's failure from another's) live in ``dispatch.DispatchQueue``, not
here - that keeps each plugin's code small and easy to test on its own.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import VisionEvent


class BasePlugin(ABC):
    """Base class for all downstream delivery plugins."""

    #: Short, stable name used in logs and in ``config/plugins.yaml``.
    name: str = "base"

    #: Whether the dispatch queue should retry (with backoff) on failure.
    #: Only plugins whose failure mode is "transient network blip" (like a
    #: webhook POST) should set this; a bug in a logging plugin retrying
    #: forever would just waste queue capacity.
    retryable: bool = False

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config: dict[str, Any] = config or {}

    @abstractmethod
    async def handle_event(self, event: VisionEvent) -> None:
        """Deliver a single event downstream. Raise on failure."""
        raise NotImplementedError
