"""Forward each event to a downstream HTTP webhook.

This plugin makes exactly one delivery attempt per call - retry-with-backoff
is handled centrally by ``dispatch.DispatchQueue`` (this plugin just has to
set ``retryable = True`` and expose ``max_retries`` / ``base_delay_seconds``
/ ``backoff_factor`` so the queue knows how to retry it). Keeping retry logic
out of the plugin makes both pieces easier to test in isolation.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..models import VisionEvent
from .base import BasePlugin


class WebhookDeliveryError(Exception):
    """Raised when a downstream webhook delivery attempt fails."""


class WebhookForwarderPlugin(BasePlugin):
    name = "webhook_forwarder"
    retryable = True

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.url: str | None = self.config.get("url")
        self.timeout_seconds: float = float(self.config.get("timeout_seconds", 5.0))
        # Read by DispatchQueue when retrying a failed delivery.
        self.max_retries: int = int(self.config.get("max_retries", 3))
        self.base_delay_seconds: float = float(self.config.get("base_delay_seconds", 0.5))
        self.backoff_factor: float = float(self.config.get("backoff_factor", 2.0))

    async def handle_event(self, event: VisionEvent) -> None:
        if not self.url:
            raise WebhookDeliveryError("webhook_forwarder plugin has no configured 'url'")

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(self.url, json=event.model_dump(mode="json"))

        if response.status_code >= 400:
            raise WebhookDeliveryError(
                f"downstream webhook at {self.url} returned "
                f"{response.status_code}: {response.text[:200]}"
            )
