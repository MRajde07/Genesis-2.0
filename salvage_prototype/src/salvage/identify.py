"""Format identification facade."""
from .formats.registry import PluginRegistry, default_registry


def identify(data: bytes, registry: PluginRegistry | None = None):
    return (registry or default_registry()).select(data)
