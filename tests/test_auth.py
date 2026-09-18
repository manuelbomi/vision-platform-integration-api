"""Unit-level checks for the API key store itself (below the HTTP layer)."""

from __future__ import annotations

from api.auth import create_api_key, hash_key, is_valid_api_key


def test_created_key_is_valid_and_stored_hashed(tmp_path) -> None:
    db_path = str(tmp_path / "keys.db")
    raw_key = create_api_key(db_path, "unit-test-key")

    assert is_valid_api_key(db_path, raw_key) is True

    import sqlite3

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT key_hash FROM api_keys WHERE name = ?", ("unit-test-key",)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == hash_key(raw_key)
    assert row[0] != raw_key  # never store the raw key


def test_unknown_key_is_invalid(tmp_path) -> None:
    db_path = str(tmp_path / "keys.db")
    create_api_key(db_path, "some-other-key")
    assert is_valid_api_key(db_path, "totally-made-up-key") is False


def test_empty_key_is_invalid(tmp_path) -> None:
    db_path = str(tmp_path / "keys.db")
    assert is_valid_api_key(db_path, "") is False
