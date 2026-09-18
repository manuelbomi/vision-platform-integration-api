#!/usr/bin/env python
"""Mint a new API key for local development.

Usage:
    python scripts/create_api_key.py "my dev key"

The raw key is printed once and only once - only its hash is stored. Save
it somewhere safe (a local .env, a secrets manager, ...); there is no way
to retrieve it again after this.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running this script directly without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from api.auth import create_api_key  # noqa: E402
from api.config import settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new API key for local/dev use")
    parser.add_argument(
        "name",
        nargs="?",
        default="local-dev",
        help="Human-readable label for this key (default: local-dev)",
    )
    args = parser.parse_args()

    raw_key = create_api_key(settings.api_keys_db_path, args.name)

    print("API key created. This is shown only once - store it securely.")
    print(f"  name: {args.name}")
    print(f"  key:  {raw_key}")
    print()
    print("Use it in requests with the X-API-Key header, e.g.:")
    print(f'  curl -H "X-API-Key: {raw_key}" ...')


if __name__ == "__main__":
    main()
