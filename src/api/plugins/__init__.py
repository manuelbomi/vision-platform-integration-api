"""Downstream delivery plugins.

Each plugin implements ``BasePlugin.handle_event`` and is responsible for
getting a normalized event to exactly one downstream system (a webhook, a
chat channel, an audit log, ...). Plugins are enabled and configured via
``config/plugins.yaml`` and loaded dynamically by ``loader.load_plugins``.
"""

from .base import BasePlugin

__all__ = ["BasePlugin"]
