"""Adapter for an ONVIF-metadata-shaped payload.

Real ONVIF analytics metadata is XML (the ``tt:`` Metadata Stream schema).
Plenty of VMS bridges forward it to HTTP webhooks as a JSON translation of
that same structure instead - deeply nested, PascalCase, and shaped nothing
like our own schema. This adapter shows how a second vendor with a
completely different payload shape still ends up as the same
``VisionEvent``.

Example payload (simplified from the ONVIF object-detection metadata
structure)::

    {
      "UtcTime": "2026-09-18T12:00:05.123Z",
      "Source": {"VideoSourceConfigurationToken": "cam-07"},
      "Data": {
        "Frame": {
          "ObjectId": "12",
          "ClassDescriptor": {
            "ClassCandidate": [{"Type": "Human", "Likelihood": 0.87}]
          },
          "BoundingBox": {"left": 100, "top": 50, "right": 300, "bottom": 400}
        }
      }
    }
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..models import BoundingBox, VisionEvent
from .base import Adapter
from .timeutil import parse_timestamp

#: Map ONVIF's coarse object classes onto our own event_type vocabulary.
_TYPE_TO_EVENT = {
    "human": "person_detected",
    "vehicle": "vehicle_detected",
    "animal": "animal_detected",
}


class OnvifMetadataAdapter(Adapter):
    name = "onvif_metadata"

    def to_vision_event(self, raw_payload: dict) -> VisionEvent:
        if not isinstance(raw_payload, dict):
            raise ValueError("onvif_metadata payload must be a JSON object")

        try:
            camera_id = str(raw_payload["Source"]["VideoSourceConfigurationToken"])
            frame = raw_payload["Data"]["Frame"]
            candidates = frame["ClassDescriptor"]["ClassCandidate"]
            if not candidates:
                raise ValueError("ClassCandidate list is empty")
            best = max(candidates, key=lambda c: float(c.get("Likelihood", 0.0)))
            confidence = float(best["Likelihood"])
            class_type = str(best.get("Type", "unknown")).lower()

            bbox = frame["BoundingBox"]
            left, top = float(bbox["left"]), float(bbox["top"])
            right, bottom = float(bbox["right"]), float(bbox["bottom"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError(f"onvif_metadata payload is missing/malformed field: {exc}") from exc

        bounding_box = BoundingBox(x=left, y=top, width=right - left, height=bottom - top)
        event_type = _TYPE_TO_EVENT.get(class_type, f"{class_type}_detected")

        utc_time = raw_payload.get("UtcTime")
        timestamp = parse_timestamp(utc_time) if utc_time else datetime.now(UTC)

        metadata = {
            "object_id": frame.get("ObjectId"),
            "class_type": class_type,
            "source_protocol": "onvif_metadata",
        }

        return VisionEvent(
            camera_id=camera_id,
            event_type=event_type,
            confidence=confidence,
            bounding_box=bounding_box,
            timestamp=timestamp,
            metadata=metadata,
        )
