"""Simple API-key authentication.

Keys are random tokens minted with ``scripts/create_api_key.py``. Only a
SHA-256 hash of each key is ever stored, so the SQLite file itself isn't a
secret if it leaks. See the README for why this is a reasonable choice for
server-to-server integrations and what a stricter enterprise rollout
(mTLS/OAuth2) would add on top.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from pathlib import Path

from fastapi import Header, HTTPException, status

from .config import settings


def _connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def init_auth_db(db_path: str) -> None:
    """Create the api_keys table if it doesn't already exist."""
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_hash TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def create_api_key(db_path: str, name: str) -> str:
    """Mint a new API key, store only its hash, and return the raw key.

    The raw key is only ever available at creation time - callers must save
    it immediately (this is the same UX as most cloud provider API keys).
    """
    init_auth_db(db_path)
    raw_key = secrets.token_urlsafe(32)
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO api_keys (key_hash, name) VALUES (?, ?)",
            (hash_key(raw_key), name),
        )
        conn.commit()
    finally:
        conn.close()
    return raw_key


def is_valid_api_key(db_path: str, raw_key: str) -> bool:
    if not raw_key:
        return False
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM api_keys WHERE key_hash = ? AND active = 1",
            (hash_key(raw_key),),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    """FastAPI dependency enforcing API-key auth on a route.

    Missing header -> 401 (you never authenticated).
    Present but invalid/unknown key -> 403 (you authenticated, not allowed).
    """
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")
    if not is_valid_api_key(settings.api_keys_db_path, x_api_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    return x_api_key
