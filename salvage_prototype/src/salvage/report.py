"""Compatibility facade; report JSON shaping lives in output.py."""
from typing import Any
from .output import shape_report


def build_report(results: list[dict[str, Any]], failures: list[dict[str, Any]] | None = None,
                 byte_ranges: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    return shape_report(results, failures, byte_ranges)
