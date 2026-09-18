"""Common event schema shared by every adapter, plugin, and endpoint.

Every camera/VMS vendor payload gets translated into a ``VisionEvent`` by an
adapter (see ``src/api/adapters/``) before anything else in the system ever
touches it. Everything downstream of that point - auth, rate limiting,
dispatch, plugins - only ever deals with this one shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """A detection bounding box.

    Units are intentionally left up to the source (normalized 0-1 floats or
    raw pixel coordinates both work) - this API treats the box as opaque
    geometry and simply passes it through to downstream systems.
    """

    x: float
    y: float
    width: float
    height: float


class VisionEvent(BaseModel):
    """The normalized event shape every adapter must produce.

    This is the single contract the rest of the system depends on. As long
    as an adapter can build one of these from a vendor's payload, every
    plugin (webhook forwarder, Slack notifier, SQL logger, ...) works with
    it unchanged.
    """

    camera_id: str = Field(..., description="Stable identifier for the source camera/sensor")
    event_type: str = Field(..., description="e.g. person_detected, vehicle_detected, loitering")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence, 0.0-1.0")
    bounding_box: BoundingBox | None = Field(default=None, description="Detection box, if any")
    timestamp: datetime = Field(..., description="When the detection occurred (source clock)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Vendor-specific extras")
