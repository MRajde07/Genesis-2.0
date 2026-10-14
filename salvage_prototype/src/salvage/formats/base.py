"""Shared contracts for SALVAGE format plugins."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Damage:
    """Structured diagnostic for damaged or undecodable bytes.

    ``offset`` is zero-based. For a short read it identifies the first missing
    byte; for a decoding error it identifies the start of the affected bytes.
    ``expected`` and ``found`` describe the requested and available byte counts.
    """
    field: str
    offset: int
    expected: int
    found: int
    reason: str
    byte_range: tuple[int, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        item: dict[str, Any] = {
            "field": self.field,
            "offset": self.offset,
            "expected": self.expected,
            "found": self.found,
            "reason": self.reason,
        }
        if self.byte_range is not None:
            item["byte_range"] = {"start": self.byte_range[0], "end": self.byte_range[1]}
        return item


@dataclass
class Result:
    """Decoded records and any structured damage found while decoding."""
    records: list[dict[str, Any]] = field(default_factory=list)
    damage: list[Damage | dict[str, Any]] = field(default_factory=list)
    format: str = "UNKNOWN"
    status: str = "unsupported"
    data: Any = None
    errors: list[str] = field(default_factory=list)


class FormatPlugin:
    """Base class for offline format decoders."""
    name = "UNKNOWN"

    def detect(self, data: bytes) -> float:
        raise NotImplementedError

    def decode(self, data: bytes) -> Result:
        raise NotImplementedError
