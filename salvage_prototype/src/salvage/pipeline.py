"""File processing pipeline. Plugin failures are isolated per input."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from .formats.base import Result
from .formats.registry import PluginRegistry, default_registry
from .bytemap import build_bytemap
from .identify import identify
from .output import shape_failure, shape_result


def _fill_bytemap(sink: dict[str, Any], data: bytes, decoded: Any, plugin: Any, shaped: dict[str, Any]) -> None:
    """Byte coverage map; failure here must never affect the recovery result."""
    try:
        raw = getattr(decoded, "data", None)
        spans = raw.get("_spans") if isinstance(raw, dict) else None
        header_length = getattr(plugin, "header_length", None)
        sink.update(build_bytemap(data, plugin_spans=spans, records=shaped.get("records"),
                                  damage=shaped.get("damage"),
                                  header_length=header_length if isinstance(header_length, int) else None))
    except Exception as error:
        sink.clear()
        sink["_error"] = f"{type(error).__name__}: {error}"


def inspect_bytes(file_name: str, data: bytes, registry: PluginRegistry | None = None,
                  debug: bool = False, bytemap_sink: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or default_registry()
    try:
        candidates = identify(data, registry)
        selected = next((candidate for candidate in candidates if candidate.get("selected")), None)
        plugin = selected["plugin"] if selected is not None else registry.select(data)
        try:
            decoded = plugin.decode(data)
            if not isinstance(decoded, Result):
                raise TypeError("decoder did not return Result")
            shaped = shape_result(file_name, decoded, fallback_format=plugin.name,
                                  identification=candidates, debug=debug)
            if bytemap_sink is not None:
                _fill_bytemap(bytemap_sink, data, decoded, plugin, shaped)
            return shaped
        except Exception as error:
            return shape_failure(file_name, plugin.name,
                                 f"Decoder failed: {type(error).__name__}: {error}", field="decoder")
    except Exception as error:
        return shape_failure(file_name, "UNKNOWN",
                             f"Processing failed: {type(error).__name__}: {error}", field="pipeline")


def inspect_file(file_path: Path, registry: PluginRegistry | None = None,
                 debug: bool = False, bytemap_sink: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        data = file_path.read_bytes()
    except Exception as error:
        return shape_failure(file_path.name, "UNKNOWN",
                             f"Could not read file: {type(error).__name__}: {error}", field="file_read")
    return inspect_bytes(file_path.name, data, registry, debug=debug, bytemap_sink=bytemap_sink)
