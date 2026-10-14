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

    def select(self, data: bytes) -> FormatPlugin:
        best: FormatPlugin | None = None
        best_confidence = -1.0
        for plugin in self._plugins:
            try:
                confidence = float(plugin.detect(data))
                if not 0.0 <= confidence <= 1.0:
                    confidence = 0.0
            except Exception:
                confidence = 0.0
            if confidence > best_confidence:
                best, best_confidence = plugin, confidence
        return best if best is not None else GenericPlugin()


def default_registry() -> PluginRegistry:
    return PluginRegistry()
