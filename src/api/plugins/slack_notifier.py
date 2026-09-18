"""Post a formatted notification to a Slack incoming webhook.

The webhook URL is never hardcoded or checked into config - it is read from
an environment variable at call time (the variable *name* is configurable,
the value is a secret that only exists in the deployment environment). If
the variable isn't set, this plugin logs and skips instead of raising, so a
missing/optional integration never blocks other plugins.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..models import VisionEvent
from .base import BasePlugin

logger = logging.getLogger(__name__)


class SlackNotifierPlugin(BasePlugin):
    name = "slack_notifier"
    retryable = False

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        # Name of the env var holding the real Slack incoming-webhook URL.
        # Never put an actual webhook URL in config/plugins.yaml or in code.
        self.webhook_env_var: str = self.config.get("webhook_env_var", "SLACK_WEBHOOK_URL")
        self.timeout_seconds: float = float(self.config.get("timeout_seconds", 5.0))

    async def handle_event(self, event: VisionEvent) -> None:
        webhook_url = os.getenv(self.webhook_env_var)
        if not webhook_url:
            logger.info(
                "slack_notifier: env var %s is not set, skipping notification for camera %s",
                self.webhook_env_var,
                event.camera_id,
            )
            return

        text = (
            f":camera: *{event.event_type}* detected on camera `{event.camera_id}` "
            f"(confidence {event.confidence:.2f}) at {event.timestamp.isoformat()}"
        )
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(webhook_url, json={"text": text})
        response.raise_for_status()
