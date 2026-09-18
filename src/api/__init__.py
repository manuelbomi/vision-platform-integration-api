"""Vision Platform Integration API.

A small FastAPI gateway that normalizes camera/VMS vendor events into a
common schema and forwards them to downstream systems (webhooks, chat,
audit databases, ...) via a plugin architecture.
"""
