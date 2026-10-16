"""Declarative learned-format specifications and their interpreter."""
from __future__ import annotations

from pathlib import Path

from .interpreter import SpecPlugin
from .spec import PluginSpec


def load_specs(directory: str | Path | None = None) -> list[SpecPlugin]:
    root = Path(directory) if directory is not None else Path(__file__).with_name("specs")
    plugins = []
    for path in sorted(root.glob("*.json")):
        plugins.append(SpecPlugin(PluginSpec.load(path)))
    return plugins


__all__ = ["PluginSpec", "SpecPlugin", "load_specs"]
