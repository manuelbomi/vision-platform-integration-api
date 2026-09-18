"""POST /webhooks/events: auth, validation, and async dispatch to plugins."""

from __future__ import annotations

import time

VALID_PAYLOAD = {
    "camera_id": "cam-1",
    "event_type": "person_detected",
    "confidence": 0.87,
    "bounding_box": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
    "timestamp": "2026-09-18T12:00:00Z",
    "metadata": {"zone": "lobby"},
}


def _wait_until(condition, timeout: float = 2.0, interval: float = 0.02) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return condition()


def test_valid_event_is_accepted_and_dispatched_to_plugin(client_factory) -> None:
    client, key, plugins = client_factory()
    recorder = plugins[0]

    with client:
        resp = client.post("/webhooks/events", json=VALID_PAYLOAD, headers={"X-API-Key": key})
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "accepted"
        assert body["event"]["camera_id"] == "cam-1"

        assert _wait_until(lambda: len(recorder.calls) == 1)
        assert recorder.calls[0].camera_id == "cam-1"
        assert recorder.calls[0].event_type == "person_detected"


def test_onvif_adapter_selectable_via_query_param(client_factory) -> None:
    client, key, plugins = client_factory()
    recorder = plugins[0]
    onvif_payload = {
        "UtcTime": "2026-09-18T10:05:00.500Z",
        "Source": {"VideoSourceConfigurationToken": "cam-07"},
        "Data": {
            "Frame": {
                "ObjectId": "12",
                "ClassDescriptor": {"ClassCandidate": [{"Type": "Human", "Likelihood": 0.87}]},
                "BoundingBox": {"left": 100, "top": 50, "right": 300, "bottom": 400},
            }
        },
    }

    with client:
        resp = client.post(
            "/webhooks/events?adapter=onvif_metadata",
            json=onvif_payload,
            headers={"X-API-Key": key},
        )
        assert resp.status_code == 202
        assert resp.json()["event"]["camera_id"] == "cam-07"
        assert _wait_until(lambda: len(recorder.calls) == 1)


def test_missing_api_key_returns_401(client_factory) -> None:
    client, _key, _plugins = client_factory()
    with client:
        resp = client.post("/webhooks/events", json=VALID_PAYLOAD)
        assert resp.status_code == 401


def test_invalid_api_key_returns_403(client_factory) -> None:
    client, _key, _plugins = client_factory()
    with client:
        resp = client.post(
            "/webhooks/events", json=VALID_PAYLOAD, headers={"X-API-Key": "not-a-real-key"}
        )
        assert resp.status_code == 403


def test_malformed_payload_returns_422(client_factory) -> None:
    client, key, _plugins = client_factory()
    with client:
        resp = client.post(
            "/webhooks/events",
            json={"camera_id": "cam-1"},  # missing event_type/confidence
            headers={"X-API-Key": key},
        )
        assert resp.status_code == 422


def test_out_of_range_confidence_returns_422(client_factory) -> None:
    client, key, _plugins = client_factory()
    with client:
        resp = client.post(
            "/webhooks/events",
            json={"camera_id": "cam-1", "event_type": "motion", "confidence": 5.0},
            headers={"X-API-Key": key},
        )
        assert resp.status_code == 422


def test_unknown_adapter_returns_422(client_factory) -> None:
    client, key, _plugins = client_factory()
    with client:
        resp = client.post(
            "/webhooks/events?adapter=not_a_real_adapter",
            json=VALID_PAYLOAD,
            headers={"X-API-Key": key},
        )
        assert resp.status_code == 422


def test_health_and_ready_endpoints(client_factory) -> None:
    client, _key, _plugins = client_factory()
    with client:
        health_resp = client.get("/health")
        assert health_resp.status_code == 200
        assert health_resp.json() == {"status": "ok"}

        ready_resp = client.get("/ready")
        assert ready_resp.status_code == 200
        assert ready_resp.json()["status"] == "ready"


def test_docs_available(client_factory) -> None:
    client, _key, _plugins = client_factory()
    with client:
        resp = client.get("/docs")
        assert resp.status_code == 200
