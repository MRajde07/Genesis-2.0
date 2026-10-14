"""File processing pipeline. Plugin failures are isolated per input."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from .formats.base import Result
from .formats.registry import PluginRegistry, default_registry
from .output import shape_failure, shape_result


def inspect_bytes(file_name: str, data: bytes, registry: PluginRegistry | None = None) -> dict[str, Any]:
    registry = registry or default_registry()
    try:
        plugin = registry.select(data)
        try:
            decoded = plugin.decode(data)
            if not isinstance(decoded, Result):
                raise TypeError("decoder did not return Result")
            return shape_result(file_name, decoded, fallback_format=plugin.name)
        except Exception as error:
            return shape_failure(file_name, plugin.name,
                                 f"Decoder failed: {type(error).__name__}: {error}", field="decoder")
    except Exception as error:
        return shape_failure(file_name, "UNKNOWN",
                             f"Processing failed: {type(error).__name__}: {error}", field="pipeline")


def inspect_file(file_path: Path, registry: PluginRegistry | None = None) -> dict[str, Any]:
    try:
        data = file_path.read_bytes()
    except Exception as error:
        return shape_failure(file_path.name, "UNKNOWN",
                             f"Could not read file: {type(error).__name__}: {error}", field="file_read")
    return inspect_bytes(file_path.name, data, registry)
