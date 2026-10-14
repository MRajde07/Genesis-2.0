"""Shared contracts for SALVAGE format plugins."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol


@dataclass
class Damage:
    """A recoverable or unrecoverable problem tied to a byte range."""
    message: str
    start: int | None = None
    end: int | None = None

    def to_dict(self) -> dict[str, Any]:
        item: dict[str, Any] = {"message": self.message}
        if self.start is not None:
            item["start"] = self.start
        if self.end is not None:
            item["end"] = self.end
        return item


@dataclass
class Result:
    """Decoded records and any damage found while decoding."""
    records: List[Dict[str, Any]] = field(default_factory=list)
    damage: List[Damage] = field(default_factory=list)
    format: str = "UNKNOWN"
    status: str = "unsupported"
    data: Any = None
    errors: List[str] = field(default_factory=list)


class FormatPlugin:
    """Base class for offline format decoders.

    ``detect`` returns a confidence in the inclusive range [0.0, 1.0].
    ``decode`` returns a Result and must not assume the input is valid.
    """
    name = "UNKNOWN"

    def detect(self, data: bytes) -> float:
        raise NotImplementedError

    def decode(self, data: bytes) -> Result:
        raise NotImplementedError
