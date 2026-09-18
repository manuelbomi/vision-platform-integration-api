"""Dynamically load and instantiate plugins from ``config/plugins.yaml``.

Keeping this separate from ``main.py`` means the app-wiring code never has
to know the concrete plugin classes exist - it just asks the loader for
"whatever is enabled right now".
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

import yaml

from .base import BasePlugin

logger = logging.getLogger(__name__)


def load_plugins(config_path: str) -> list[BasePlugin]:
    """Load every plugin marked ``enabled: true`` in the given YAML file.

    Returns an empty list (rather than raising) if the config file does not
    exist, so a fresh checkout without any config still boots.
    """
    path = Path(config_path)
    if not path.exists():
        logger.warning("Plugin config file %s not found; starting with no plugins", config_path)
        return []

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    plugins: list[BasePlugin] = []
    for entry in data.get("plugins", []):
        if not entry.get("enabled", False):
            continue
        module_name = entry["module"]
        class_name = entry["class"]
        module = importlib.import_module(module_name)
        plugin_cls = getattr(module, class_name)
        plugin: BasePlugin = plugin_cls(entry.get("config", {}))
        plugins.append(plugin)
        logger.info("Loaded plugin '%s' (%s.%s)", plugin.name, module_name, class_name)

    return plugins
