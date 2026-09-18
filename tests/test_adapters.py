"""Each adapter: raw vendor payload -> correct VisionEvent fields."""

from __future__ import annotations

import pytest

from api.adapters.generic_json import GenericJsonAdapter
from api.adapters.onvif_metadata import OnvifMetadataAdapter


def test_generic_json_adapter_maps_fields() -> None:
    adapter = GenericJsonAdapter()
    raw = {
        "camera_id": "cam-42",
        "event_type": "loitering",
        "confidence": 0.75,
        "bounding_box": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
        "timestamp": "2026-09-18T10:00:00Z",
        "metadata": {"zone": "entrance"},
    }

    event = adapter.to_vision_event(raw)

    assert event.camera_id == "cam-42"
    assert event.event_type == "loitering"
    assert event.confidence == 0.75
    assert event.bounding_box is not None
    assert event.bounding_box.width == 0.2
    assert event.metadata["zone"] == "entrance"


def test_generic_json_adapter_fills_in_defaults() -> None:
    adapter = GenericJsonAdapter()
    raw = {"camera_id": "cam-1", "event_type": "motion", "confidence": 0.5}

    event = adapter.to_vision_event(raw)

    assert event.bounding_box is None
    assert event.metadata == {}
    assert event.timestamp is not None


def test_generic_json_adapter_raises_on_missing_field() -> None:
    adapter = GenericJsonAdapter()
    with pytest.raises(ValueError):
        adapter.to_vision_event({"camera_id": "cam-1"})


def test_onvif_metadata_adapter_maps_fields() -> None:
    adapter = OnvifMetadataAdapter()
    raw = {
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

    event = adapter.to_vision_event(raw)

    assert event.camera_id == "cam-07"
    assert event.event_type == "person_detected"
    assert event.confidence == 0.87
    assert event.bounding_box is not None
    assert event.bounding_box.x == 100
    assert event.bounding_box.y == 50
    assert event.bounding_box.width == 200
    assert event.bounding_box.height == 350
    assert event.metadata["object_id"] == "12"
    assert event.metadata["class_type"] == "human"


def test_onvif_metadata_adapter_picks_highest_likelihood_candidate() -> None:
    adapter = OnvifMetadataAdapter()
    raw = {
        "Source": {"VideoSourceConfigurationToken": "cam-09"},
        "Data": {
            "Frame": {
                "ClassDescriptor": {
                    "ClassCandidate": [
                        {"Type": "Vehicle", "Likelihood": 0.3},
                        {"Type": "Human", "Likelihood": 0.91},
                    ]
                },
                "BoundingBox": {"left": 0, "top": 0, "right": 10, "bottom": 10},
            }
        },
    }

    event = adapter.to_vision_event(raw)

    assert event.event_type == "person_detected"
    assert event.confidence == 0.91


def test_onvif_metadata_adapter_raises_on_malformed_payload() -> None:
    adapter = OnvifMetadataAdapter()
    with pytest.raises(ValueError):
        adapter.to_vision_event({"nonsense": True})
