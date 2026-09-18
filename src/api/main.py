"""FastAPI app wiring: adapters + auth + rate limiting + dispatch + plugins.

Run locally with::

    uvicorn api.main:app --app-dir src --reload

See the README for the full setup walkthrough, including how to mint an
API key and send a sample event with curl.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Body, Depends, FastAPI, HTTPException, Query, status
from pydantic import ValidationError

from .adapters import ADAPTER_REGISTRY
from .auth import init_auth_db
from .config import settings
from .dispatch import DispatchQueue
from .plugins.base import BasePlugin
from .plugins.loader import load_plugins
from .ratelimit import enforce_rate_limit

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app(plugins: list[BasePlugin] | None = None) -> FastAPI:
    """Build a FastAPI app instance.

    ``plugins``, if given, overrides the plugins that would otherwise be
    loaded from ``config/plugins.yaml``. This is mainly for tests, which
    want to inject a fake plugin that records calls instead of hitting the
    filesystem/network.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_auth_db(settings.api_keys_db_path)
        active_plugins = (
            plugins if plugins is not None else load_plugins(settings.plugins_config_path)
        )
        app.state.plugins = active_plugins
        app.state.dispatch_queue = DispatchQueue(
            active_plugins, num_workers=settings.dispatch_workers
        )
        await app.state.dispatch_queue.start()
        logger.info("Startup complete. Active plugins: %s", [p.name for p in active_plugins])

        yield

        await app.state.dispatch_queue.stop()

    app = FastAPI(
        title="Vision Platform Integration API",
        description=(
            "Integration gateway that normalizes camera/VMS vendor events into a "
            "common schema and forwards them to downstream systems via plugins."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.get("/health", tags=["ops"], summary="Liveness probe")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/ready", tags=["ops"], summary="Readiness probe")
    async def ready() -> dict:
        dispatch_queue: DispatchQueue | None = getattr(app.state, "dispatch_queue", None)
        if dispatch_queue is None or not dispatch_queue.is_running:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="dispatch queue is not running",
            )
        return {"status": "ready", "plugins": [p.name for p in app.state.plugins]}

    @app.post(
        "/webhooks/events",
        status_code=status.HTTP_202_ACCEPTED,
        tags=["events"],
        summary="Receive a vendor event, normalize it, and dispatch it to plugins",
    )
    async def receive_event(
        payload: dict = Body(..., description="Raw vendor payload"),
        adapter: str = Query(
            "generic_json",
            description=f"Adapter to normalize with. Available: {list(ADAPTER_REGISTRY)}",
        ),
        api_key: str = Depends(enforce_rate_limit),
    ) -> dict:
        chosen_adapter = ADAPTER_REGISTRY.get(adapter)
        if chosen_adapter is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Unknown adapter '{adapter}'. Available: {list(ADAPTER_REGISTRY)}",
            )

        try:
            event = chosen_adapter.to_vision_event(payload)
        except (ValueError, ValidationError, KeyError, TypeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Could not normalize payload with adapter '{adapter}': {exc}",
            ) from exc

        await app.state.dispatch_queue.enqueue(event)
        return {"status": "accepted", "event": event.model_dump(mode="json")}

    return app


app = create_app()
