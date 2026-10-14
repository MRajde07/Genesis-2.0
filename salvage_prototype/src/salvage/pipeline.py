"""File processing pipeline. Decoder failures are isolated per input."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from .formats.base import Result
from .formats.registry import PluginRegistry, default_registry


def inspect_bytes(file_name: str, data: bytes, registry: PluginRegistry | None = None) -> dict[str, Any]:
    registry = registry or default_registry()
    try:
        plugin = registry.select(data)
        try:
            decoded = plugin.decode(data)
            if not isinstance(decoded, Result):
                raise TypeError("decoder did not return Result")
            result = {
                "file_name": file_name,
                "format": decoded.format or plugin.name,
                "status": decoded.status,
                "data": decoded.data,
                "errors": list(decoded.errors),
            }
            if decoded.damage:
                result["damage"] = [item.to_dict() for item in decoded.damage]
            return result
        except Exception as error:
            return {"file_name": file_name, "format": plugin.name, "status": "error",
                    "data": None, "errors": [f"Decoder failed: {type(error).__name__}: {error}"]}
    except Exception as error:
        return {"file_name": file_name, "format": "UNKNOWN", "status": "error",
                "data": None, "errors": [f"Processing failed: {type(error).__name__}: {error}"]}


def inspect_file(file_path: Path, registry: PluginRegistry | None = None) -> dict[str, Any]:
    try:
        data = file_path.read_bytes()
    except Exception as error:
        return {"file_name": file_path.name, "format": "UNKNOWN", "status": "error",
                "data": None, "errors": [f"Could not read file: {type(error).__name__}: {error}"]}
    return inspect_bytes(file_path.name, data, registry)
