"""Adapter interface.

Every vendor/protocol integration implements this one method. Adapters
should raise ``ValueError`` (or let a ``pydantic.ValidationError`` bubble
up) when a payload is missing required fields or otherwise malformed - the
API layer turns that into an HTTP 422 response.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import VisionEvent


class Adapter(ABC):
    """Base class for all vendor payload adapters."""

    #: Short, stable name used to select this adapter (e.g. via a query param).
    name: str = "base"

    @abstractmethod
    def to_vision_event(self, raw_payload: dict) -> VisionEvent:
        """Convert a raw vendor payload into a normalized ``VisionEvent``.

        Implementations should raise ``ValueError`` for malformed input.
        """
        raise NotImplementedError
