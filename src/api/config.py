"""Runtime configuration, read from environment variables at import time.

Kept deliberately simple (a plain dataclass, no extra dependency) since this
is a small, single-process service. A larger deployment would swap this for
a settings library backed by a secrets manager - see the README's
"Limitations & production hardening notes".
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    api_keys_db_path: str = os.getenv("API_KEYS_DB_PATH", "data/api_keys.db")
    events_db_path: str = os.getenv("EVENTS_DB_PATH", "data/events.db")
    plugins_config_path: str = os.getenv("PLUGINS_CONFIG_PATH", "config/plugins.yaml")
    rate_limit_capacity: int = int(os.getenv("RATE_LIMIT_CAPACITY", "20"))
    rate_limit_refill_per_sec: float = float(os.getenv("RATE_LIMIT_REFILL_PER_SEC", "5"))
    dispatch_workers: int = int(os.getenv("DISPATCH_WORKERS", "2"))


# A single, mutable settings instance. Tests are free to overwrite fields on
# this object (e.g. ``settings.api_keys_db_path = str(tmp_path / "keys.db")``)
# before building an app, since nothing here is cached at import time.
settings = Settings()
