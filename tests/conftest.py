"""Shared pytest fixtures.

Each test that talks to the HTTP layer gets its own isolated API-key
database (via `tmp_path`) and a fresh rate limiter, so tests never see
state left behind by another test.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import ratelimit
from api.auth import create_api_key, init_auth_db
from api.config import settings
from api.main import create_app

from .fakes import RecordingPlugin


@pytest.fixture()
def client_factory(tmp_path):
    """Returns a builder function: build_client(capacity=..., refill=...).

    Gives each test full control over rate-limit settings without needing
    to repeat the same six lines of setup everywhere.
    """

    def build(
        capacity: int = 1000,
        refill_per_sec: float = 1000.0,
        plugins: list | None = None,
    ):
        settings.api_keys_db_path = str(tmp_path / "api_keys.db")
        settings.rate_limit_capacity = capacity
        settings.rate_limit_refill_per_sec = refill_per_sec
        ratelimit.reset_rate_limiter()
        init_auth_db(settings.api_keys_db_path)
        raw_key = create_api_key(settings.api_keys_db_path, "test-key")

        active_plugins = plugins if plugins is not None else [RecordingPlugin()]
        app = create_app(plugins=active_plugins)
        client = TestClient(app)
        return client, raw_key, active_plugins

    return build
