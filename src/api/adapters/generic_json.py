"""Adapter for an already-normalized-ish JSON payload.

This covers vendors (or in-house camera agents) that already emit
something close to our own schema - field names line up almost 1:1, so this
adapter is mostly validation and light coercion (e.g. filling in a missing
timestamp, defaulting metadata to an empty dict).

Example payload::

    {
      "camera_id": "cam-01",
      "event_type": "person_detected",
      "confidence": 0.92,
      "bounding_box": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
      "timestamp": "2026-09-18T12:00:00Z",
      "metadata": {"zone": "lobby"}
    }
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..models import BoundingBox, VisionEvent
from .base import Adapter
from .timeutil import parse_timestamp


class GenericJsonAdapter(Adapter):
    name = "generic_json"

    def to_vision_event(self, raw_payload: dict) -> VisionEvent:
        if not isinstance(raw_payload, dict):
            raise ValueError("generic_json payload must be a JSON object")

        try:
            camera_id = str(raw_payload["camera_id"])
            event_type = str(raw_payload["event_type"])
            confidence = float(raw_payload["confidence"])
        except KeyError as exc:
            raise ValueError(f"generic_json payload missing required field: {exc}") from exc
        except (TypeError, ValueError) as exc:
            raise ValueError(f"generic_json payload has a badly typed field: {exc}") from exc

        bbox_raw = raw_payload.get("bounding_box")
        bounding_box = BoundingBox(**bbox_raw) if bbox_raw else None

        timestamp_raw = raw_payload.get("timestamp")
        timestamp = parse_timestamp(timestamp_raw) if timestamp_raw else datetime.now(UTC)

        metadata = raw_payload.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError("generic_json payload 'metadata' must be an object")

        return VisionEvent(
            camera_id=camera_id,
            event_type=event_type,
            confidence=confidence,
            bounding_box=bounding_box,
            timestamp=timestamp,
            metadata=metadata,
        )
