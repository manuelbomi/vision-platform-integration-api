"""GET /events/recent, GET /events/stats, GET /plugins.

These are read-only, additive endpoints: `/events/recent` and
`/events/stats` read from the exact SQLite table the `sql_logger` plugin
already writes (see `src/api/plugins/sql_logger.py`), and `/plugins`
reflects `config/plugins.yaml`. The key thing under test is the full,
real path: an event goes in through the normal webhook + dispatch queue,
the real `SqlLoggerPlugin` (not a fake) persists it, and the new endpoint
reads it back out.
"""

from __future__ import annotations

import time

import yaml

from api.config import settings
from api.plugins.sql_logger import SqlLoggerPlugin

VALID_PAYLOAD = {
    "camera_id": "cam-9",
    "event_type": "loitering",
    "confidence": 0.75,
    "bounding_box": {"x": 0.0, "y": 0.1, "width": 0.2, "height": 0.3},
    "timestamp": "2026-09-18T09:00:00Z",
    "metadata": {"zone": "dock"},
}


def _wait_until(condition, timeout: float = 2.0, interval: float = 0.02) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return condition()


def test_recent_events_reflects_events_logged_via_real_dispatch_path(
    client_factory, tmp_path
) -> None:
    events_db = str(tmp_path / "events.db")
    settings.events_db_path = events_db

    sql_logger = SqlLoggerPlugin({"db_path": events_db})
    client, key, _plugins = client_factory(plugins=[sql_logger])

    with client:
        resp = client.post("/webhooks/events", json=VALID_PAYLOAD, headers={"X-API-Key": key})
        assert resp.status_code == 202

        def _logged() -> bool:
            r = client.get("/events/recent", headers={"X-API-Key": key})
            return r.status_code == 200 and len(r.json()) == 1

        assert _wait_until(_logged)

        listing = client.get("/events/recent", headers={"X-API-Key": key})
        assert listing.status_code == 200
        body = listing.json()
        assert len(body) == 1
        event = body[0]
        assert event["camera_id"] == "cam-9"
        assert event["event_type"] == "loitering"
        assert event["confidence"] == 0.75
        assert "timestamp" in event
        assert "received_at" in event


def test_recent_events_requires_api_key(client_factory, tmp_path) -> None:
    settings.events_db_path = str(tmp_path / "events.db")
    client, _key, _plugins = client_factory()
    with client:
        resp = client.get("/events/recent")
        assert resp.status_code == 401


def test_recent_events_respects_limit_and_newest_first(client_factory, tmp_path) -> None:
    events_db = str(tmp_path / "events.db")
    settings.events_db_path = events_db
    # Force a single dispatch worker so events are persisted in the same
    # order they were submitted - with the default of 2+ workers, dispatch
    # is deliberately concurrent and insertion order isn't guaranteed.
    settings.dispatch_workers = 1

    sql_logger = SqlLoggerPlugin({"db_path": events_db})
    client, key, _plugins = client_factory(plugins=[sql_logger])

    try:
        with client:
            for i in range(3):
                payload = dict(VALID_PAYLOAD, camera_id=f"cam-{i}")
                resp = client.post(
                    "/webhooks/events", json=payload, headers={"X-API-Key": key}
                )
                assert resp.status_code == 202

            def _all_logged() -> bool:
                r = client.get("/events/recent?limit=10", headers={"X-API-Key": key})
                return r.status_code == 200 and len(r.json()) == 3

            assert _wait_until(_all_logged)

            limited = client.get("/events/recent?limit=1", headers={"X-API-Key": key})
            assert limited.status_code == 200
            body = limited.json()
            assert len(body) == 1
            # Most recently-inserted row (cam-2) should come back first.
            assert body[0]["camera_id"] == "cam-2"
    finally:
        settings.dispatch_workers = 2


def test_recent_events_empty_when_nothing_logged_yet(client_factory, tmp_path) -> None:
    settings.events_db_path = str(tmp_path / "never-created.db")
    client, key, _plugins = client_factory()
    with client:
        resp = client.get("/events/recent", headers={"X-API-Key": key})
        assert resp.status_code == 200
        assert resp.json() == []


def test_event_stats_requires_api_key_and_aggregates(client_factory, tmp_path) -> None:
    events_db = str(tmp_path / "events.db")
    settings.events_db_path = events_db

    sql_logger = SqlLoggerPlugin({"db_path": events_db})
    client, key, _plugins = client_factory(plugins=[sql_logger])

    with client:
        unauthed = client.get("/events/stats")
        assert unauthed.status_code == 401

        client.post("/webhooks/events", json=VALID_PAYLOAD, headers={"X-API-Key": key})

        def _counted() -> bool:
            r = client.get("/events/stats", headers={"X-API-Key": key})
            return r.status_code == 200 and r.json()["total_events"] == 1

        assert _wait_until(_counted)

        stats = client.get("/events/stats", headers={"X-API-Key": key}).json()
        assert stats["events_by_type"] == {"loitering": 1}
        assert stats["events_by_camera"] == {"cam-9": 1}


def test_plugins_endpoint_reports_config_yaml(client_factory, tmp_path) -> None:
    config_path = tmp_path / "plugins.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "plugins": [
                    {
                        "name": "sql_logger",
                        "module": "api.plugins.sql_logger",
                        "class": "SqlLoggerPlugin",
                        "enabled": True,
                        "config": {"db_path": str(tmp_path / "events.db")},
                    },
                    {
                        "name": "slack_notifier",
                        "module": "api.plugins.slack_notifier",
                        "class": "SlackNotifierPlugin",
                        "enabled": False,
                        "config": {},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    settings.plugins_config_path = str(config_path)

    client, key, _plugins = client_factory()
    with client:
        unauthed = client.get("/plugins")
        assert unauthed.status_code == 401

        resp = client.get("/plugins", headers={"X-API-Key": key})
        assert resp.status_code == 200
        by_name = {p["name"]: p for p in resp.json()}
        assert by_name["sql_logger"]["enabled"] is True
        assert by_name["slack_notifier"]["enabled"] is False
