"""Bounds-checked byte reader with deterministic damage diagnostics.

Offsets and ranges are zero-based and half-open. Reads never raise merely
because the requested range extends beyond the supplied buffer.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ByteOrder = Literal["big", "little"]


@dataclass(frozen=True)
class ReadDamage:
    field: str
    offset: int
    expected: int
    found: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "offset": self.offset,
            "expected": self.expected,
            "found": self.found,
            "reason": self.reason,
        }


class ByteReader:
    """Read bytes and integers without out-of-range exceptions.

    ``read`` advances the cursor and returns every available byte. Short reads
    append a structured entry to ``damage``. ``read_at`` does not move the
    cursor. ``read_uint`` decodes the available portion of a short integer (or
    returns ``None`` when no bytes are available), using the configured byte
    order. For short little-endian integers, missing high-order bytes are
    treated as zero; for short big-endian integers, available bytes form the
    integer as written.
    """

    def __init__(self, data: bytes | bytearray | memoryview, endian: ByteOrder = "big"):
        if endian not in ("big", "little"):
            raise ValueError("endian must be 'big' or 'little'")
        self._data = bytes(data)
        self.endian: ByteOrder = endian
        self.offset = 0
        self.damage: list[dict[str, Any]] = []

    @property
    def size(self) -> int:
        return len(self._data)

    @property
    def remaining(self) -> int:
        return max(0, self.size - self.offset)

    def _read_at(self, offset: int, size: int, field: str) -> bytes:
        # Invalid ranges are diagnosed and produce no bytes, rather than
        # allowing Python's negative-slice semantics to hide a caller bug.
        if size < 0:
            self.damage.append(ReadDamage(field, offset, size, 0, "negative read size").to_dict())
            return b""
        if offset < 0:
            self.damage.append(ReadDamage(field, offset, size, 0, "negative offset").to_dict())
            return b""
        if offset >= self.size:
            available = 0
        else:
            available = min(size, self.size - offset)
        chunk = self._data[offset:offset + available] if available else b""
        if available < size:
            self.damage.append(ReadDamage(
                field=field,
                offset=offset + available,
                expected=size,
                found=available,
                reason="out of range: insufficient bytes",
            ).to_dict())
        return chunk

    def read(self, size: int, field: str = "") -> bytes:
        """Return available bytes at the cursor and advance by requested size.

        The cursor advances by the requested size, clamped to the end of the
        buffer. Invalid negative sizes do not move it.
        """
        start = self.offset
        result = self._read_at(start, size, field)
        if size >= 0:
            self.offset = min(self.size, start + size)
        return result

    def read_at(self, offset: int, size: int, field: str = "") -> bytes:
        """Return available bytes at an absolute offset without moving cursor."""
        return self._read_at(offset, size, field)

    def read_uint(
        self,
        size: int,
        field: str = "",
        *,
        endian: ByteOrder | None = None,
        signed: bool = False,
    ) -> int | None:
        """Read an unsigned/signed integer, preserving short-read diagnostics."""
        order = endian or self.endian
        if order not in ("big", "little"):
            self.damage.append(ReadDamage(field, self.offset, size, 0, "invalid byte order").to_dict())
            return None
        start = self.offset
        raw = self.read(size, field)
        if not raw:
            return None
        if size <= 0:
            return None
        if signed and len(raw) == size:
            return int.from_bytes(raw, order, signed=True)
        value = int.from_bytes(raw, order, signed=False)
        if signed and len(raw) < size:
            bits = len(raw) * 8
            if order == "big" and raw[0] & 0x80:
                value -= 1 << bits
            elif order == "little" and raw[-1] & 0x80:
                value -= 1 << bits
        return value

    def seek(self, offset: int, field: str = "cursor") -> bool:
        """Move cursor if offset is valid; otherwise record damage and clamp."""
        if offset < 0 or offset > self.size:
            self.damage.append(ReadDamage(
                field, offset, self.size, max(0, min(offset, self.size)),
                "seek offset out of range",
            ).to_dict())
            self.offset = max(0, min(offset, self.size))
            return False
        self.offset = offset
        return True


def read_bytes(path: Path) -> bytes:
    """Compatibility helper retained for callers that need whole-file reads."""
    return path.read_bytes()
