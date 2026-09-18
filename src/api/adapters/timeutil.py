"""Small shared helper for parsing vendor timestamps.

Kept out of any one adapter module so both ``generic_json`` and
``onvif_metadata`` (and any future adapter) can reuse it.
"""

from __future__ import annotations

from datetime import datetime


def parse_timestamp(value: object) -> datetime:
    """Parse a vendor timestamp into a timezone-aware ``datetime``.

    Accepts an already-parsed ``datetime``, or an ISO-8601 string. Handles
    the trailing ``Z`` (Zulu/UTC) suffix that Python's ``fromisoformat``
    does not accept on its own in older versions.
    """
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)
