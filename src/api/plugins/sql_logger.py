"""Write every event to a local SQLite table for audit/history.

Uses plain ``sqlite3`` (no ORM needed for one table) run through
``asyncio.to_thread`` so the blocking DB calls don't stall the event loop
that also has to run every other plugin and serve HTTP requests.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

from ..models import VisionEvent
from .base import BasePlugin


class SqlLoggerPlugin(BasePlugin):
    name = "sql_logger"
    retryable = False

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.db_path: str = self.config.get("db_path", "data/events.db")
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.db_path)

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    event_timestamp TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    received_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _insert(self, event: VisionEvent) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO events
                    (camera_id, event_type, confidence, event_timestamp, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.camera_id,
                    event.event_type,
                    event.confidence,
                    event.timestamp.isoformat(),
                    event.model_dump_json(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    async def handle_event(self, event: VisionEvent) -> None:
        await asyncio.to_thread(self._insert, event)
