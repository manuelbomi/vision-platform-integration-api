"""Vendor payload adapters.

Each adapter knows how to turn one vendor/protocol's payload shape into a
``VisionEvent``. Add a new camera/VMS vendor by adding a new adapter here -
nothing else in the system needs to change.
"""

from .base import Adapter
from .generic_json import GenericJsonAdapter
from .onvif_metadata import OnvifMetadataAdapter

#: Registry of adapters available to the API, keyed by the name clients
#: pass in the ``adapter`` query parameter on ``POST /webhooks/events``.
ADAPTER_REGISTRY: dict[str, Adapter] = {
    "generic_json": GenericJsonAdapter(),
    "onvif_metadata": OnvifMetadataAdapter(),
}

__all__ = ["Adapter", "GenericJsonAdapter", "OnvifMetadataAdapter", "ADAPTER_REGISTRY"]
