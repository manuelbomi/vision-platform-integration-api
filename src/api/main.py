"""FastAPI app wiring: adapters + auth + rate limiting + dispatch + plugins.

Run locally with::

    uvicorn api.main:app --app-dir src --reload

See the README for the full setup walkthrough, including how to mint an
API key and send a sample event with curl.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Body, Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError

from .adapters import ADAPTER_REGISTRY
from .auth import init_auth_db, require_api_key
from .config import settings
from .dispatch import DispatchQueue
from .models import VisionEvent
from .plugins.base import BasePlugin
from .plugins.loader import list_configured_plugins, load_plugins
from .ratelimit import enforce_rate_limit

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RecentEvent(VisionEvent):
    """A ``VisionEvent`` as read back from the ``sql_logger`` audit table.

    Adds ``received_at`` (when this service persisted it), which isn't part
    of the core event contract but is useful for a dashboard.
    """

    received_at: str = Field(..., description="When the sql_logger plugin persisted this event")


class EventStats(BaseModel):
    """Aggregate counts over the logged events table."""

    total_events: int
    events_by_type: dict[str, int]
    events_by_camera: dict[str, int]


class PluginInfo(BaseModel):
    """A plugin declared in ``config/plugins.yaml``, enabled or not."""

    name: str
    module: str
    class_name: str
    enabled: bool


def _fetch_recent_events(db_path: str, limit: int) -> list[RecentEvent]:
    """Read the most recently logged events from the sql_logger's SQLite table.

    Reuses the exact table/schema ``SqlLoggerPlugin`` already writes
    (``events``, see ``src/api/plugins/sql_logger.py``) instead of creating a
    second, divergent one. If the table doesn't exist yet (e.g. the
    sql_logger plugin is disabled, or nothing has been logged yet), this
    returns an empty list rather than erroring.
    """
    conn = sqlite3.connect(db_path)
    try:
        try:
            rows = conn.execute(
                "SELECT payload_json, received_at FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    finally:
        conn.close()

    events: list[RecentEvent] = []
    for payload_json, received_at in rows:
        data = json.loads(payload_json)
        data["received_at"] = received_at
        events.append(RecentEvent.model_validate(data))
    return events


def _fetch_event_stats(db_path: str) -> EventStats:
    """Aggregate counts over the same sql_logger events table."""
    conn = sqlite3.connect(db_path)
    try:
        try:
            total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            by_type = dict(
                conn.execute(
                    "SELECT event_type, COUNT(*) FROM events GROUP BY event_type"
                ).fetchall()
            )
            by_camera = dict(
                conn.execute(
                    "SELECT camera_id, COUNT(*) FROM events GROUP BY camera_id"
                ).fetchall()
            )
        except sqlite3.OperationalError:
            return EventStats(total_events=0, events_by_type={}, events_by_camera={})
    finally:
        conn.close()
    return EventStats(total_events=total, events_by_type=by_type, events_by_camera=by_camera)


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

    # Lets a browser-based client (the admin dashboard in frontend/, served
    # from its own origin/port) call this API directly. Purely additive:
    # requests without an Origin header (curl, server-to-server, the test
    # client) are completely unaffected.
    origins = settings.cors_allowed_origins.split(",") if settings.cors_allowed_origins else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
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

    @app.get(
        "/events/recent",
        tags=["events"],
        summary="List the most recently logged events (read-only, audit-log backed)",
        response_model=list[RecentEvent],
    )
    async def list_recent_events(
        limit: int = Query(
            50, ge=1, le=500, description="Max number of events to return, newest first"
        ),
        api_key: str = Depends(require_api_key),
    ) -> list[RecentEvent]:
        return await asyncio.to_thread(_fetch_recent_events, settings.events_db_path, limit)

    @app.get(
        "/events/stats",
        tags=["events"],
        summary="Aggregate counts over logged events (by type and by camera)",
        response_model=EventStats,
    )
    async def event_stats(api_key: str = Depends(require_api_key)) -> EventStats:
        return await asyncio.to_thread(_fetch_event_stats, settings.events_db_path)

    @app.get(
        "/plugins",
        tags=["ops"],
        summary="List plugins declared in config/plugins.yaml and whether each is enabled",
        response_model=list[PluginInfo],
    )
    async def list_plugins(api_key: str = Depends(require_api_key)) -> list[PluginInfo]:
        return [
            PluginInfo(**entry)
            for entry in list_configured_plugins(settings.plugins_config_path)
        ]

    return app


app = create_app()
