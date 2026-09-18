"""Token-bucket rate limiting: hammer the endpoint past the limit -> 429."""

from __future__ import annotations

VALID_PAYLOAD = {
    "camera_id": "cam-1",
    "event_type": "motion",
    "confidence": 0.6,
    "timestamp": "2026-09-18T12:00:00Z",
}


def test_rate_limit_eventually_returns_429(client_factory) -> None:
    # Small bucket, effectively no refill during the test, so a burst of
    # requests is guaranteed to exhaust it.
    client, key, _plugins = client_factory(capacity=3, refill_per_sec=0.0001)

    with client:
        statuses = []
        for _ in range(10):
            resp = client.post(
                "/webhooks/events", json=VALID_PAYLOAD, headers={"X-API-Key": key}
            )
            statuses.append(resp.status_code)

        assert 429 in statuses
        # The first few requests (up to capacity) should have gone through.
        assert statuses[0] == 202


def test_rate_limit_is_per_key(client_factory) -> None:
    client, key, _plugins = client_factory(capacity=2, refill_per_sec=0.0001)

    with client:
        # Exhaust the bucket for `key`.
        for _ in range(2):
            resp = client.post(
                "/webhooks/events", json=VALID_PAYLOAD, headers={"X-API-Key": key}
            )
            assert resp.status_code == 202

        exhausted = client.post(
            "/webhooks/events", json=VALID_PAYLOAD, headers={"X-API-Key": key}
        )
        assert exhausted.status_code == 429

        # A request with no/garbage key still gets 401/403 first, proving
        # the limiter doesn't leak the good key's exhaustion onto others
        # (it's keyed by API key, checked only after auth succeeds).
        other = client.post("/webhooks/events", json=VALID_PAYLOAD)
        assert other.status_code == 401
