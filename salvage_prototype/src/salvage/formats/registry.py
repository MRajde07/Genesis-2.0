"""Deterministic plugin registry and confidence-based selection."""
from __future__ import annotations

from .base import FormatPlugin
from .generic import GenericPlugin
from .stud import STUDPlugin


class PluginRegistry:
    def __init__(self, plugins: list[FormatPlugin] | None = None):
        self._plugins: list[FormatPlugin] = list(plugins or [STUDPlugin(), GenericPlugin()])

    def register(self, plugin: FormatPlugin) -> None:
        self._plugins.append(plugin)

    @property
    def plugins(self) -> tuple[FormatPlugin, ...]:
        return tuple(self._plugins)

    def select(self, data: bytes, threshold: float = 0.55) -> FormatPlugin:
        # Local import avoids a module cycle: identify consumes the registry.
        from ..identify import select_plugin
        return select_plugin(data, registry=self, threshold=threshold)


def default_registry() -> PluginRegistry:
    return PluginRegistry()
